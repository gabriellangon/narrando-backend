-- ============================================================================
-- NARRANDO - Database Tables, Functions, and Triggers
-- ============================================================================
-- This file contains all custom SQL for the Narrando application
-- including beta users system and credit transaction logging
-- ============================================================================

-- ============================================================================
-- TABLE: beta_users
-- ============================================================================
-- Stores emails of beta users who will receive free credits upon signup
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.beta_users (
    email TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enable RLS on beta_users
ALTER TABLE public.beta_users ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Only service_role can manage beta_users
CREATE POLICY "Service role can manage beta_users"
    ON public.beta_users
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

COMMENT ON TABLE public.beta_users IS 'List of beta user emails who receive free credits on signup';
COMMENT ON COLUMN public.beta_users.email IS 'Email address of beta user (must match users.email)';


-- ============================================================================
-- TABLE: credit_transactions
-- ============================================================================
-- Logs all credit transactions (purchases and consumptions) for audit trail
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.credit_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('purchase', 'consumption')),
    source TEXT NOT NULL DEFAULT 'iap' CHECK (source IN ('beta', 'iap', 'promo')),
    tour_id UUID REFERENCES public.guided_tours(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index for faster queries by user_id
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id
    ON public.credit_transactions(user_id);

-- Create index for faster queries by created_at
CREATE INDEX IF NOT EXISTS idx_credit_transactions_created_at
    ON public.credit_transactions(created_at DESC);

-- Enable RLS on credit_transactions
ALTER TABLE public.credit_transactions ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only view their own transactions
CREATE POLICY "Users can view own credit transactions"
    ON public.credit_transactions
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- RLS Policy: Only service_role can insert transactions (via RPC)
CREATE POLICY "Service role can insert credit transactions"
    ON public.credit_transactions
    FOR INSERT
    TO service_role
    WITH CHECK (true);

-- RLS Policy: No updates allowed (immutable audit log)
CREATE POLICY "No updates allowed on credit transactions"
    ON public.credit_transactions
    FOR UPDATE
    TO authenticated
    USING (false);

-- RLS Policy: No deletes allowed (immutable audit log)
CREATE POLICY "No deletes allowed on credit transactions"
    ON public.credit_transactions
    FOR DELETE
    TO authenticated
    USING (false);

COMMENT ON TABLE public.credit_transactions IS 'Audit log of all credit purchases and consumptions';
COMMENT ON COLUMN public.credit_transactions.user_id IS 'User who performed the transaction';
COMMENT ON COLUMN public.credit_transactions.amount IS 'Number of credits (positive for purchase, negative for consumption)';
COMMENT ON COLUMN public.credit_transactions.transaction_type IS 'Type: purchase or consumption';
COMMENT ON COLUMN public.credit_transactions.source IS 'Source: beta (beta user bonus), iap (in-app purchase), promo (promotional)';
COMMENT ON COLUMN public.credit_transactions.tour_id IS 'Tour ID for consumption transactions (NULL for purchases)';

-- ============================================================================
-- USERS: revenuecat_user_id support
-- ============================================================================
-- Stores the RevenueCat user identifier used for purchases
-- ============================================================================

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS revenuecat_user_id TEXT;

-- Ensure uniqueness when provided
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_revenuecat_user_id_unique
    ON public.users(revenuecat_user_id)
    WHERE revenuecat_user_id IS NOT NULL;

COMMENT ON COLUMN public.users.revenuecat_user_id IS 'RevenueCat app user identifier for this account';

-- RPC to set the RevenueCat user id for the authenticated user (or service_role)
CREATE OR REPLACE FUNCTION public.set_revenuecat_user_id(
    p_user_id UUID,
    p_revenuecat_user_id TEXT
)
RETURNS public.users
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
    v_caller uuid;
    v_user public.users%ROWTYPE;
BEGIN
    -- If not service_role, enforce that caller matches p_user_id
    IF current_setting('request.jwt.claim.role', true) IS NULL
       OR current_setting('request.jwt.claim.role', true) <> 'service_role' THEN
        SELECT auth.uid() INTO v_caller;
        IF v_caller IS NULL OR v_caller <> p_user_id THEN
            RAISE EXCEPTION 'Not authorized to update revenuecat_user_id';
        END IF;
    END IF;

    UPDATE public.users
    SET revenuecat_user_id = p_revenuecat_user_id,
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING * INTO v_user;

    RETURN v_user;
END;
$$;

COMMENT ON FUNCTION public.set_revenuecat_user_id IS 'Sets the RevenueCat app user id for the given user (self or service_role)';


-- ============================================================================
-- FUNCTION: log_credit_transaction
-- ============================================================================
-- Centralized function to log all credit transactions
-- Called from:
--   1. Flutter app after IAP purchase
--   2. consume_tour_credits_for_generation RPC
--   3. Beta user signup trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION public.log_credit_transaction(
    p_user_id UUID,
    p_amount INTEGER,
    p_transaction_type TEXT,
    p_source TEXT DEFAULT 'iap',
    p_tour_id UUID DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
    -- Elevate to service_role to bypass RLS
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);

    -- Validate transaction_type
    IF p_transaction_type NOT IN ('purchase', 'consumption') THEN
        RAISE EXCEPTION 'Invalid transaction_type: %. Must be purchase or consumption', p_transaction_type;
    END IF;

    -- Validate source
    IF p_source NOT IN ('beta', 'iap', 'promo') THEN
        RAISE EXCEPTION 'Invalid source: %. Must be beta, iap, or promo', p_source;
    END IF;

    -- Validate amount sign based on transaction type
    IF p_transaction_type = 'purchase' AND p_amount <= 0 THEN
        RAISE EXCEPTION 'Purchase transactions must have positive amount';
    END IF;

    IF p_transaction_type = 'consumption' AND p_amount >= 0 THEN
        RAISE EXCEPTION 'Consumption transactions must have negative amount';
    END IF;

    -- Insert transaction log
    INSERT INTO public.credit_transactions (
        user_id,
        amount,
        transaction_type,
        source,
        tour_id
    ) VALUES (
        p_user_id,
        p_amount,
        p_transaction_type,
        p_source,
        p_tour_id
    );

    RAISE NOTICE 'Logged % transaction: user=%, amount=%, source=%, tour=%',
        p_transaction_type, p_user_id, p_amount, p_source, p_tour_id;

END;
$$;

COMMENT ON FUNCTION public.log_credit_transaction IS 'Logs a credit transaction (purchase or consumption) with validation';


-- ============================================================================
-- FUNCTION: handle_beta_user_signup
-- ============================================================================
-- Trigger function that runs after a new user is created
-- Checks if user email is in beta_users table
-- If yes: adds 5 free credits, logs transaction, removes from beta_users
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_beta_user_signup()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
    v_beta_email TEXT;
    v_bonus_credits INTEGER := 5;
BEGIN
    -- Elevate to service_role to bypass RLS
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);

    -- Check if user's email is in beta_users table
    SELECT email INTO v_beta_email
    FROM public.beta_users
    WHERE LOWER(email) = LOWER(NEW.email);

    -- If user is a beta user
    IF v_beta_email IS NOT NULL THEN
        -- Add bonus credits to user
        UPDATE public.users
        SET credits = COALESCE(credits, 0) + v_bonus_credits,
            updated_at = NOW()
        WHERE id = NEW.id;

        -- Log the transaction
        PERFORM log_credit_transaction(
            p_user_id := NEW.id,
            p_amount := v_bonus_credits,
            p_transaction_type := 'purchase',
            p_source := 'beta',
            p_tour_id := NULL
        );

        -- Remove email from beta_users table (one-time bonus)
        DELETE FROM public.beta_users
        WHERE LOWER(email) = LOWER(NEW.email);

        RAISE NOTICE 'Beta user signup: % received % credits', NEW.email, v_bonus_credits;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_beta_user_signup IS 'Automatically grants beta users 5 free credits on signup';


-- ============================================================================
-- TRIGGER: on_user_created_check_beta
-- ============================================================================
-- Fires after a new user is inserted in the users table
-- Calls handle_beta_user_signup to check for beta user bonus
-- ============================================================================

DROP TRIGGER IF EXISTS on_user_created_check_beta ON public.users;

CREATE TRIGGER on_user_created_check_beta
    AFTER INSERT ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_beta_user_signup();

COMMENT ON TRIGGER on_user_created_check_beta ON public.users IS 'Checks if new user is beta user and grants bonus credits';


-- ============================================================================
-- MODIFIED FUNCTION: consume_tour_credits_for_generation
-- ============================================================================
-- Original function with added transaction logging
-- Now logs every credit consumption in credit_transactions table
-- ============================================================================

CREATE OR REPLACE FUNCTION public.consume_tour_credits_for_generation(
    tour_id_param uuid,
    user_id_param uuid
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    required_credits INTEGER;
    updated_user RECORD;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);

    -- Count required credits (number of tour points)
    SELECT COUNT(*)
    INTO required_credits
    FROM tour_points
    WHERE tour_id = tour_id_param;

    IF required_credits <= 0 THEN
        RETURN json_build_object(
            'success', false,
            'message', 'Tour has no attractions to generate',
            'required_credits', 0
        );
    END IF;

    -- Deduct credits from user
    UPDATE users
    SET credits = credits - required_credits,
        updated_at = NOW()
    WHERE id = user_id_param
      AND credits >= required_credits
    RETURNING credits
    INTO updated_user;

    IF NOT FOUND THEN
        RETURN json_build_object(
            'success', false,
            'message', 'Insufficient credits',
            'required_credits', required_credits
        );
    END IF;

    -- ( NEW: Log the credit consumption transaction
    PERFORM log_credit_transaction(
        p_user_id := user_id_param,
        p_amount := -required_credits,  -- Negative for consumption
        p_transaction_type := 'consumption',
        p_source := 'iap',
        p_tour_id := tour_id_param
    );

    RETURN json_build_object(
        'success', true,
        'required_credits', required_credits,
        'remaining_credits', updated_user.credits
    );
END;
$function$;

-- =====================================================================
-- Union: user active guided + custom tours (for "My Tours")
-- =====================================================================
CREATE OR REPLACE FUNCTION public.get_user_active_all_tours(
    p_user_id UUID,
    p_language_code TEXT DEFAULT 'en'
)
RETURNS TABLE(
    user_id UUID,
    purchase_id UUID,
    source TEXT,
    purchase_date TIMESTAMPTZ,
    quantity_total INTEGER,
    quantity_completed INTEGER,
    quantity_gifted INTEGER,
    tour_id UUID,
    tour_name VARCHAR,
    city VARCHAR,
    country VARCHAR,
    language_code TEXT,
    place_id TEXT,
    total_distance INTEGER,
    estimated_walking_time INTEGER,
    point_count INTEGER,
    first_point_name VARCHAR,
    first_point_address TEXT,
    first_point_photos JSONB,
    tour_type TEXT
) AS $function$
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);
    p_language_code := COALESCE(NULLIF(p_language_code, ''), 'en');

    RETURN QUERY
    (
      SELECT
        tpur.user_id,
        tpur.id AS purchase_id,
        tpur.source::text,
        tpur.purchase_date,
        tpur.quantity_total,
        tpur.quantity_completed,
        tpur.quantity_gifted,
        gt.id AS tour_id,
        COALESCE(gtt.tour_name, gt.tour_name) AS tour_name,
        COALESCE(ct.city, c.city) AS city,
        COALESCE(ct.country, c.country) AS country,
        tpur.language_code::text,
        c.place_id::text,
        gt.total_distance,
        gt.estimated_walking_time,
        gt.point_count,
        COALESCE(first_trans.name, first_point.name) AS first_point_name,
        first_point.formatted_address AS first_point_address,
        first_point.photos AS first_point_photos,
        'auto'::text AS tour_type
      FROM tour_purchases tpur
      JOIN guided_tours gt ON tpur.tour_id = gt.id
      JOIN cities c ON gt.city_id = c.id
      LEFT JOIN guided_tour_translations gtt
        ON gtt.tour_id = gt.id AND gtt.language_code = p_language_code
      LEFT JOIN city_translations ct
        ON ct.city_id = c.id AND ct.language_code = p_language_code
      LEFT JOIN tour_points tp
        ON gt.id = tp.tour_id AND tp.point_order = 1
      LEFT JOIN attractions first_point
        ON tp.attraction_id = first_point.id
      LEFT JOIN attraction_translations first_trans
        ON first_trans.attraction_id = first_point.id
       AND first_trans.language_code = p_language_code
      WHERE tpur.user_id = p_user_id
        AND tpur.quantity_total > tpur.quantity_gifted
    )
    UNION ALL
    (
      SELECT
        utp.user_id,
        utp.id AS purchase_id,
        utp.source,
        utp.purchase_date,
        utp.quantity_total,
        utp.quantity_completed,
        utp.quantity_gifted,
        utp.user_tour_id AS tour_id,
        ut.name AS tour_name,
        c.city,
        c.country,
        utp.language_code,
        c.place_id,
        ut.total_distance,
        ut.estimated_walking_time,
        ut.point_count,
        fp.name AS first_point_name,
        fp.formatted_address AS first_point_address,
        fp.photos AS first_point_photos,
        'custom'::text AS tour_type
      FROM user_tour_purchases utp
      JOIN user_tours ut ON ut.id = utp.user_tour_id
      JOIN cities c ON c.id = ut.city_id
      LEFT JOIN LATERAL (
        SELECT
          COALESCE(at.name, a.name) AS name,
          a.formatted_address,
          a.photos
        FROM user_tour_points utp2
        JOIN attractions a ON utp2.attraction_id = a.id
        LEFT JOIN attraction_translations at
          ON at.attraction_id = a.id
         AND at.language_code = p_language_code
        WHERE utp2.user_tour_id = ut.id
        ORDER BY COALESCE(utp2.point_order, utp2.global_index, 999999)
        LIMIT 1
      ) fp ON TRUE
      WHERE utp.user_id = p_user_id
        AND utp.quantity_total > utp.quantity_gifted
    )
    ORDER BY purchase_date DESC;
END;
$function$ LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'public';

-- =====================================================================
-- Drafts: user custom tours without a purchase
-- =====================================================================
CREATE OR REPLACE FUNCTION public.get_user_custom_tour_drafts(
    p_user_id UUID,
    p_language_code TEXT DEFAULT 'en'
)
RETURNS TABLE(
    tour_id UUID,
    tour_name TEXT,
    city TEXT,
    country TEXT,
    place_id TEXT,
    total_distance INTEGER,
    estimated_walking_time INTEGER,
    point_count INTEGER,
    created_at TIMESTAMPTZ,
    first_point_name TEXT,
    first_point_address TEXT,
    first_point_photos JSONB,
    tour_type TEXT
) AS $function$
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);
    p_language_code := COALESCE(NULLIF(p_language_code, ''), 'en');

    RETURN QUERY
    SELECT
      ut.id AS tour_id,
      ut.name::text AS tour_name,
      c.city::text AS city,
      c.country::text AS country,
      c.place_id::text AS place_id,
      ut.total_distance,
      ut.estimated_walking_time,
      ut.point_count,
      ut.created_at,
      fp.name::text AS first_point_name,
      fp.formatted_address::text AS first_point_address,
      fp.photos AS first_point_photos,
      'custom'::text AS tour_type
    FROM user_tours ut
    JOIN cities c ON c.id = ut.city_id
    LEFT JOIN LATERAL (
      SELECT
        COALESCE(at.name, a.name) AS name,
        a.formatted_address,
        a.photos
      FROM user_tour_points utp2
      JOIN attractions a ON utp2.attraction_id = a.id
      LEFT JOIN attraction_translations at
        ON at.attraction_id = a.id
       AND at.language_code = p_language_code
      WHERE utp2.user_tour_id = ut.id
      ORDER BY COALESCE(utp2.point_order, utp2.global_index, 999999)
      LIMIT 1
    ) fp ON TRUE
    WHERE ut.user_id = p_user_id
      AND NOT EXISTS (
        SELECT 1
        FROM user_tour_purchases utp
        WHERE utp.user_tour_id = ut.id
          AND utp.user_id = p_user_id
      )
    ORDER BY ut.created_at DESC;
END;
$function$ LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'public';

-- =====================================================================
-- Delete a custom tour draft (no purchase yet)
-- =====================================================================
CREATE OR REPLACE FUNCTION public.delete_user_custom_tour_draft(
    p_user_id UUID,
    p_tour_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);

    DELETE FROM user_tours
    WHERE id = p_tour_id
      AND user_id = p_user_id;
END;
$function$;

COMMENT ON FUNCTION public.consume_tour_credits_for_generation IS 'Consumes credits for tour generation and logs transaction';

-- =====================================================================
-- Helper: base URL for VPS API calls (configurable via app.narrando_api_base_url)
-- =====================================================================
CREATE OR REPLACE FUNCTION public.narrando_api_base_url()
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    configured_url TEXT;
BEGIN
    configured_url := current_setting('app.narrando_api_base_url', true);
    RETURN COALESCE(NULLIF(configured_url, ''), 'http://localhost:5000');
END;
$function$;

COMMENT ON FUNCTION public.narrando_api_base_url IS 'Base URL for Narrando API on the VPS (set app.narrando_api_base_url in the database)';

-- =====================================================================
-- Déclenchement de la génération côté VPS (custom tours)
-- =====================================================================
CREATE OR REPLACE FUNCTION public.trigger_user_tour_full_generation(
    user_tour_id_param UUID,
    user_id_param UUID,
    narration_type_param TEXT DEFAULT 'standard',
    language_code_param TEXT DEFAULT 'en'
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $function$
DECLARE
    api_base_url TEXT;
    request_url TEXT;
    request_payload JSONB;
BEGIN
    api_base_url := narrando_api_base_url();
    request_url := api_base_url || '/generate-complete-audio-custom/' || user_tour_id_param;

    request_payload := jsonb_build_object(
        'user_tour_id', user_tour_id_param,
        'user_id', user_id_param,
        'narration_type', narration_type_param,
        'language_code', language_code_param,
        'force_regenerate', false,
        'skip_audio', false,
        'token', 'o2ESQAYiP41yAO33OhRDmcqosaTsPLTdoPfpK0xtUdhtMZTfcJewm9aK2Kz7Jq8MV'
    );

    PERFORM net.http_post(
        url     := request_url,
        headers := '{"Content-Type": "application/json"}'::jsonb,
        body    := request_payload
    );

    RAISE NOTICE 'Custom generation request sent for user_tour %, narration %, language %, url %',
        user_tour_id_param, narration_type_param, language_code_param, request_url;
    RETURN TRUE;

EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error calling custom full generation endpoint: %', SQLERRM;
        RETURN FALSE;
END;
$function$;

-- ============================================================================
-- NEW FUNCTION: get_tour_preview_or_sample
-- ============================================================================
-- Returns a generated preview audio for a tour (first attraction) if available
-- for the requested narration_type/language. Otherwise falls back to the
-- generic sample audio. Keeps legacy get_audio_sample unchanged.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_tour_preview_or_sample(
    tour_id_param uuid,
    language_code_param text DEFAULT 'en'::text,
    narration_type_param text DEFAULT 'standard'::text
)
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    normalized_lang text;
    generated_audio text;
    generated_lang text;
    sample_url text;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);
    normalized_lang := COALESCE(NULLIF(TRIM(language_code_param), ''), 'en');

    -- Try to fetch generated audio on the first attraction in the requested language
    SELECT COALESCE(at_trans.audio_url, a.audio_url)->>narration_type_param,
           normalized_lang
    INTO generated_audio, generated_lang
    FROM tour_points tp
    JOIN attractions a ON tp.attraction_id = a.id
    LEFT JOIN attraction_translations at_trans
        ON at_trans.attraction_id = a.id
       AND at_trans.language_code = normalized_lang
    WHERE tp.tour_id = tour_id_param
    ORDER BY tp.point_order ASC
    LIMIT 1;

    -- Fallback: try English generated audio
    IF generated_audio IS NULL AND normalized_lang <> 'en' THEN
        SELECT COALESCE(at_trans.audio_url, a.audio_url)->>narration_type_param,
               'en'
        INTO generated_audio, generated_lang
        FROM tour_points tp
        JOIN attractions a ON tp.attraction_id = a.id
        LEFT JOIN attraction_translations at_trans
            ON at_trans.attraction_id = a.id
           AND at_trans.language_code = 'en'
        WHERE tp.tour_id = tour_id_param
        ORDER BY tp.point_order ASC
        LIMIT 1;
    END IF;

    IF generated_audio IS NOT NULL AND generated_audio <> '' THEN
        RETURN json_build_object(
            'url', generated_audio,
            'source', 'generated',
            'language_code', generated_lang
        );
    END IF;

    -- Sample fallback
    SELECT get_audio_sample(normalized_lang, narration_type_param)
    INTO sample_url;

    IF (sample_url IS NULL OR sample_url = '') AND normalized_lang <> 'en' THEN
        SELECT get_audio_sample('en', narration_type_param)
        INTO sample_url;
    END IF;

    RETURN json_build_object(
        'url', sample_url,
        'source', 'sample',
        'language_code', COALESCE(normalized_lang, 'en')
    );
END;
$function$;

COMMENT ON FUNCTION public.get_tour_preview_or_sample IS 'Returns generated preview audio for a tour if available; otherwise returns generic sample audio with source indicator.';


-- ============================================================================
-- END OF FILE
-- ============================================================================
-- All tables, functions, and triggers for beta users and credit tracking
-- ============================================================================

-- ============================================================================
-- SECTION: Custom Tours (schema + RPC stubs)
-- ============================================================================
-- Mirrors of guided stack for user-created tours. Implementations are stubs
-- and must be aligned with guided behavior before production use.
-- ============================================================================

-- Core tables
CREATE TABLE IF NOT EXISTS public.user_tours (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    city_id UUID NOT NULL REFERENCES public.cities(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    total_distance INTEGER,
    estimated_walking_time INTEGER,
    point_count INTEGER,
    cover_photo JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.user_tour_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_tour_id UUID NOT NULL REFERENCES public.user_tours(id) ON DELETE CASCADE,
    attraction_id UUID NOT NULL REFERENCES public.attractions(id) ON DELETE CASCADE,
    point_order INTEGER,
    global_index INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.user_walking_paths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_tour_id UUID NOT NULL REFERENCES public.user_tours(id) ON DELETE CASCADE,
    from_attraction_id UUID NOT NULL REFERENCES public.attractions(id) ON DELETE CASCADE,
    to_attraction_id UUID REFERENCES public.attractions(id) ON DELETE CASCADE,
    path_coordinates JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Purchases and invitations
CREATE TABLE IF NOT EXISTS public.user_tour_purchases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    user_tour_id UUID NOT NULL REFERENCES public.user_tours(id) ON DELETE CASCADE,
    quantity_total INTEGER NOT NULL DEFAULT 3,
    quantity_completed INTEGER NOT NULL DEFAULT 0,
    quantity_gifted INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'iap',
    narration_type TEXT NOT NULL DEFAULT 'standard',
    language_code TEXT NOT NULL DEFAULT 'en',
    purchase_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.user_tour_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tour_purchase_id UUID NOT NULL REFERENCES public.user_tour_purchases(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    recipient_email TEXT NOT NULL,
    recipient_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    accepted_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Processing status for custom tours
CREATE TABLE IF NOT EXISTS public.processing_user_tour_generation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_tour_id UUID NOT NULL REFERENCES public.user_tours(id) ON DELETE CASCADE,
    narration_type TEXT NOT NULL DEFAULT 'standard',
    language_code TEXT NOT NULL DEFAULT 'en',
    status TEXT NOT NULL DEFAULT 'processing',
    progress_percent INTEGER DEFAULT 0,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_processing_user_tour_unique
ON public.processing_user_tour_generation (user_tour_id, narration_type, language_code);

-- RPC stubs (to be implemented)
CREATE OR REPLACE FUNCTION public.get_complete_user_tour_with_attractions(
    tour_id_param UUID,
    language_code_param TEXT DEFAULT 'en'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    tour_record RECORD;
    points JSONB;
    walking_paths JSONB;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);
    language_code_param := COALESCE(NULLIF(language_code_param, ''), 'en');

    SELECT ut.*, c.city, c.country, c.place_id
    INTO tour_record
    FROM user_tours ut
    JOIN cities c ON c.id = ut.city_id
    WHERE ut.id = tour_id_param;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    SELECT jsonb_agg(
             jsonb_build_object(
               'attraction', jsonb_build_object(
                 'id', a.id,
                 'name', COALESCE(at.name, a.name),
                 'types', a.types,
                 'photos', a.photos,
                 'rating', a.rating,
                 'place_id', a.place_id,
                 'formatted_address', a.formatted_address,
                 'audio_url', COALESCE(at.audio_url, a.audio_url),
                 'location', jsonb_build_object(
                   'lat', a.lat::numeric,
                   'lng', a.lng::numeric
                 )
               ),
               'point_order', utp.point_order,
               'global_index', utp.global_index,
               'distance_from_previous', NULL,
               'walking_time_from_previous', NULL
             )
             ORDER BY COALESCE(utp.global_index, utp.point_order, 999999)
           )
    INTO points
    FROM user_tour_points utp
    JOIN attractions a ON utp.attraction_id = a.id
    LEFT JOIN attraction_translations at
      ON at.attraction_id = a.id
     AND at.language_code = language_code_param
    WHERE utp.user_tour_id = tour_id_param;

    SELECT jsonb_agg(
             jsonb_build_object(
               'walking_path_id', uwp.id,
               'tour_id', uwp.user_tour_id,
               'path_coordinates', uwp.path_coordinates,
               'from_attraction', jsonb_build_object(
                 'id', fa.id,
                 'name', COALESCE(fat.name, fa.name),
                 'location', jsonb_build_object(
                   'lat', fa.lat::numeric,
                   'lng', fa.lng::numeric
                 ),
                 'audio_url', COALESCE(fat.audio_url, fa.audio_url),
                 'photos', fa.photos,
                 'types', fa.types
               ),
               'to_attraction_id', uwp.to_attraction_id
             )
             ORDER BY uwp.id
           )
    INTO walking_paths
    FROM user_walking_paths uwp
    JOIN attractions fa ON uwp.from_attraction_id = fa.id
    LEFT JOIN attraction_translations fat
      ON fat.attraction_id = fa.id
     AND fat.language_code = language_code_param
    WHERE uwp.user_tour_id = tour_id_param;

    RETURN jsonb_build_object(
      'id', tour_record.id,
      'tour_id', 0,
      'tour_name', tour_record.name,
      'max_participants', 3,
      'city_id', tour_record.city_id,
      'city_name', tour_record.city,
      'country', tour_record.country,
      'place_id', tour_record.place_id,
      'total_distance', tour_record.total_distance,
      'estimated_walking_time', tour_record.estimated_walking_time,
      'point_count', tour_record.point_count,
      'cover_photo', tour_record.cover_photo,
      'points', COALESCE(points, '[]'::jsonb),
      'walking_paths', COALESCE(walking_paths, '[]'::jsonb)
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public.get_active_user_tour_model(
    tour_id_param UUID,
    language_code_param TEXT DEFAULT 'en'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    walking_paths JSONB;
    last_point JSONB;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);
    language_code_param := COALESCE(NULLIF(language_code_param, ''), 'en');

    WITH ordered_points AS (
        SELECT
            utp.user_tour_id,
            utp.attraction_id,
            COALESCE(att_trans.name, a.name) AS name,
            a.place_id,
            a.formatted_address,
            a.lat,
            a.lng,
            COALESCE(att_trans.ai_description::jsonb, a.ai_description) AS ai_description,
            a.photos,
            a.rating,
            a.types,
            COALESCE(att_trans.audio_url, a.audio_url) AS audio_url,
            ROW_NUMBER() OVER (
                ORDER BY COALESCE(utp.point_order, utp.global_index, 999999), utp.created_at, utp.attraction_id
            ) AS idx
        FROM user_tour_points utp
        JOIN attractions a ON utp.attraction_id = a.id
        LEFT JOIN attraction_translations att_trans
          ON att_trans.attraction_id = a.id
         AND att_trans.language_code = language_code_param
        WHERE utp.user_tour_id = tour_id_param
    ),
    paths AS (
        SELECT jsonb_agg(
            jsonb_build_object(
                'walking_path_id', op.idx::text, -- dummy id for ordering, as text for client parsing
                'tour_id', tour_id_param,
                'path_coordinates', jsonb_build_array(
                    jsonb_build_object('lat', op.lat::numeric, 'lng', op.lng::numeric),
                    jsonb_build_object('lat', op_next.lat::numeric, 'lng', op_next.lng::numeric)
                ),
                'from_attraction', jsonb_build_object(
                    'id', op.attraction_id,
                    'place_id', op.place_id,
                    'name', op.name,
                    'formatted_address', op.formatted_address,
                    'location', jsonb_build_object(
                        'lat', op.lat::numeric,
                        'lng', op.lng::numeric
                    ),
                    'ai_description', op.ai_description,
                    'photos', op.photos,
                    'rating', op.rating,
                    'types', op.types,
                    'audio_url', op.audio_url
                ),
                'to_attraction_id', op_next.attraction_id
            )
            ORDER BY op.idx
        ) AS walking_paths
        FROM ordered_points op
        LEFT JOIN ordered_points op_next ON op_next.idx = op.idx + 1
        WHERE op_next.attraction_id IS NOT NULL
    ),
    last_point_cte AS (
        SELECT jsonb_build_object(
            'id', op.attraction_id,
            'place_id', op.place_id,
            'name', op.name,
            'formatted_address', op.formatted_address,
            'location', jsonb_build_object('lat', op.lat::numeric, 'lng', op.lng::numeric),
            'ai_description', op.ai_description,
            'photos', op.photos,
            'rating', op.rating,
            'types', op.types,
            'audio_url', op.audio_url
        ) AS last_point
        FROM ordered_points op
        ORDER BY op.idx DESC
        LIMIT 1
    )
    SELECT p.walking_paths, lp.last_point
    INTO walking_paths, last_point
    FROM paths p
    LEFT JOIN last_point_cte lp ON TRUE;

    IF walking_paths IS NULL OR jsonb_array_length(walking_paths) = 0 THEN
        RETURN NULL;
    END IF;

    RETURN jsonb_build_object(
        'walking_paths', walking_paths,
        'last_point', last_point
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public.request_user_tour_full_generation(
    tour_id_param UUID,
    user_id_param UUID,
    narration_type_param TEXT DEFAULT 'standard',
    language_code_param TEXT DEFAULT 'en'
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    total_points INTEGER;
    points_with_audio INTEGER;
    processing_record RECORD;
    progress_percent_value INTEGER;
    user_has_purchase BOOLEAN;
    owned_languages json := '[]'::json;
    current_credits INTEGER;
    missing_credits INTEGER;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);
    language_code_param := COALESCE(NULLIF(language_code_param, ''), 'en');

    IF NOT EXISTS (SELECT 1 FROM users WHERE id = user_id_param) THEN
        RETURN json_build_object(
            'status', 'error',
            'message', 'User not found',
            'owned_languages', '[]'::json
        );
    END IF;

    SELECT EXISTS(
        SELECT 1 FROM user_tour_purchases
        WHERE user_id = user_id_param
          AND user_tour_id = tour_id_param
          AND narration_type = narration_type_param
          AND language_code = language_code_param
          AND quantity_total > quantity_gifted
    ) INTO user_has_purchase;

    SELECT COALESCE(json_agg(
        json_build_object(
            'language_code', utp.language_code,
            'purchase_id', utp.id
        )
    ), '[]'::json)
    INTO owned_languages
    FROM user_tour_purchases utp
    WHERE utp.user_id = user_id_param
      AND utp.user_tour_id = tour_id_param
      AND utp.narration_type = narration_type_param
      AND utp.quantity_total > utp.quantity_gifted;

    -- Count points for credit calculation
    SELECT COUNT(*)
    INTO total_points
    FROM user_tour_points utp
    WHERE utp.user_tour_id = tour_id_param;

    IF NOT COALESCE(user_has_purchase, false) THEN
        SELECT credits INTO current_credits FROM users WHERE id = user_id_param FOR UPDATE;
        current_credits := COALESCE(current_credits, 0);
        total_points := COALESCE(total_points, 0);

        IF current_credits < total_points THEN
            missing_credits := total_points - current_credits;
            RETURN json_build_object(
                'status', 'insufficient_credits',
                'total_points', total_points,
                'completed_points', points_with_audio,
                'user_has_purchase', false,
                'narration_type', narration_type_param,
                'language_code', language_code_param,
                'message', 'Not enough credits to generate this custom tour',
                'missing_credits', missing_credits,
                'owned_languages', owned_languages
            );
        END IF;

        UPDATE users
        SET credits = credits - total_points
        WHERE id = user_id_param;

        -- Audit: log credit consumption for custom tour generation
        PERFORM log_credit_transaction(
            p_user_id := user_id_param,
            p_amount := -total_points,
            p_transaction_type := 'consumption',
            p_source := 'iap',
            -- FK de credit_transactions pointe sur guided_tours.tour_id,
            -- on laisse NULL pour les custom afin d'éviter une violation FK.
            p_tour_id := NULL
        );

        INSERT INTO user_tour_purchases (
            user_id,
            user_tour_id,
            quantity_total,
            quantity_completed,
            quantity_gifted,
            source,
            narration_type,
            language_code
        ) VALUES (
            user_id_param,
            tour_id_param,
            3,
            0,
            0,
            'purchase',
            narration_type_param,
            language_code_param
        );

        user_has_purchase := true;

        SELECT COALESCE(json_agg(
            json_build_object(
                'language_code', utp.language_code,
                'purchase_id', utp.id
            )
        ), '[]'::json)
        INTO owned_languages
        FROM user_tour_purchases utp
        WHERE utp.user_id = user_id_param
          AND utp.user_tour_id = tour_id_param
          AND utp.narration_type = narration_type_param
          AND utp.quantity_total > utp.quantity_gifted;
    END IF;

    SELECT
        COUNT(*) AS total,
        COUNT(
            CASE
                WHEN COALESCE(at.audio_url, a.audio_url)->>narration_type_param IS NOT NULL THEN 1
            END
        ) AS with_audio
    INTO total_points, points_with_audio
    FROM user_tour_points utp
    JOIN attractions a ON utp.attraction_id = a.id
    LEFT JOIN attraction_translations at
      ON at.attraction_id = utp.attraction_id
     AND at.language_code = language_code_param
    WHERE utp.user_tour_id = tour_id_param;

    IF total_points > 0 AND total_points = points_with_audio THEN
        RETURN json_build_object(
            'status', 'ready',
            'total_points', total_points,
            'completed_points', points_with_audio,
            'user_has_purchase', COALESCE(user_has_purchase, false),
            'narration_type', narration_type_param,
            'language_code', language_code_param,
            'message', 'All tour audio files are ready',
            'owned_languages', owned_languages
        );
    END IF;

    SELECT * INTO processing_record
    FROM processing_user_tour_generation
    WHERE user_tour_id = tour_id_param
      AND narration_type = narration_type_param
      AND language_code = language_code_param;

    IF FOUND THEN
        IF processing_record.status = 'error'
           OR processing_record.requested_at < NOW() - INTERVAL '5 minutes' THEN
            DELETE FROM processing_user_tour_generation
            WHERE user_tour_id = tour_id_param
              AND narration_type = narration_type_param
              AND language_code = language_code_param;
        ELSE
            RETURN json_build_object(
                'status', 'processing',
                'requested_at', processing_record.requested_at,
                'total_points', total_points,
                'completed_points', points_with_audio,
                'narration_type', narration_type_param,
                'language_code', language_code_param,
                'message', 'Tour audio generation in progress...',
                'progress_percent', processing_record.progress_percent,
                'owned_languages', owned_languages
            );
        END IF;
    END IF;

    BEGIN
        INSERT INTO processing_user_tour_generation (
            user_tour_id, narration_type, language_code, status, requested_at, progress_percent
        )
        VALUES (tour_id_param, narration_type_param, language_code_param, 'processing', NOW(), 0);

        -- Déclenchement de la génération via l'API VPS (custom)
        PERFORM public.trigger_user_tour_full_generation(
            tour_id_param,
            user_id_param,
            narration_type_param,
            language_code_param
        );

        RETURN json_build_object(
            'status', 'processing',
            'requested_at', NOW(),
            'total_points', total_points,
            'completed_points', points_with_audio,
            'narration_type', narration_type_param,
            'language_code', language_code_param,
            'message', 'Custom tour audio generation started',
            'progress_percent', 3,
            'owned_languages', owned_languages
        );

    EXCEPTION
        WHEN unique_violation THEN
            SELECT progress_percent
            INTO progress_percent_value
            FROM processing_user_tour_generation
            WHERE user_tour_id = tour_id_param
              AND narration_type = narration_type_param
              AND language_code = language_code_param
            LIMIT 1;

            RETURN json_build_object(
                'status', 'processing',
                'narration_type', narration_type_param,
                'language_code', language_code_param,
                'message', 'Custom tour audio generation already in progress',
                'progress_percent', progress_percent_value,
                'owned_languages', owned_languages
            );
        WHEN OTHERS THEN
            DELETE FROM processing_user_tour_generation
            WHERE user_tour_id = tour_id_param
              AND narration_type = narration_type_param
              AND language_code = language_code_param;

            RETURN json_build_object(
                'status', 'error',
                'message', 'Failed to initiate custom tour audio generation: ' || SQLERRM,
                'owned_languages', owned_languages
            );
    END;
END;
$function$;

CREATE OR REPLACE FUNCTION public.check_user_tour_generation_status(
    tour_id_param UUID,
    user_id_param UUID,
    narration_type_param TEXT DEFAULT 'standard',
    language_code_param TEXT DEFAULT 'en'
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    total_points INTEGER;
    points_with_audio INTEGER;
    processing_record RECORD;
    user_has_purchase BOOLEAN;
    owned_languages json := '[]'::json;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);
    language_code_param := COALESCE(NULLIF(language_code_param, ''), 'en');

    IF NOT EXISTS (SELECT 1 FROM users WHERE id = user_id_param) THEN
        RETURN json_build_object(
            'status', 'not_started',
            'total_points', 0,
            'completed_points', 0,
            'user_has_purchase', false,
            'narration_type', narration_type_param,
            'language_code', language_code_param,
            'message', 'Ready to generate tour audio',
            'owned_languages', '[]'::json
        );
    END IF;

    SELECT EXISTS(
        SELECT 1
        FROM user_tour_purchases
        WHERE user_id = user_id_param
          AND user_tour_id = tour_id_param
          AND narration_type = narration_type_param
          AND language_code = language_code_param
          AND quantity_total > quantity_gifted
    ) INTO user_has_purchase;

    SELECT COALESCE(json_agg(
        json_build_object(
            'language_code', utp.language_code,
            'purchase_id', utp.id
        )
    ), '[]'::json)
    INTO owned_languages
    FROM user_tour_purchases utp
    WHERE utp.user_id = user_id_param
      AND utp.user_tour_id = tour_id_param
      AND utp.narration_type = narration_type_param
      AND utp.quantity_total > utp.quantity_gifted;

    SELECT
        COUNT(*) AS total,
        COUNT(
            CASE
                WHEN COALESCE(at_trans.audio_url, a.audio_url)->>narration_type_param IS NOT NULL THEN 1
            END
        ) AS with_audio
    INTO total_points, points_with_audio
    FROM user_tour_points utp
    JOIN attractions a ON utp.attraction_id = a.id
    LEFT JOIN attraction_translations at_trans
      ON at_trans.attraction_id = a.id
     AND at_trans.language_code = language_code_param
    WHERE utp.user_tour_id = tour_id_param;

    IF total_points > 0 AND total_points = points_with_audio THEN
        RETURN json_build_object(
            'status', 'ready',
            'total_points', total_points,
            'completed_points', points_with_audio,
            'user_has_purchase', COALESCE(user_has_purchase, false),
            'narration_type', narration_type_param,
            'language_code', language_code_param,
            'message', 'All tour audio files are ready',
            'owned_languages', owned_languages
        );
    END IF;

    SELECT * INTO processing_record
    FROM processing_user_tour_generation
    WHERE user_tour_id = tour_id_param
      AND narration_type = narration_type_param
      AND language_code = language_code_param;

    IF FOUND THEN
        IF processing_record.requested_at < NOW() - INTERVAL '5 minutes' THEN
            DELETE FROM processing_user_tour_generation
            WHERE user_tour_id = tour_id_param
              AND narration_type = narration_type_param
              AND language_code = language_code_param;

            RETURN json_build_object(
                'status', 'not_started',
                'total_points', total_points,
                'completed_points', points_with_audio,
                'user_has_purchase', COALESCE(user_has_purchase, false),
                'narration_type', narration_type_param,
                'language_code', language_code_param,
                'message', 'Generation not started',
                'owned_languages', owned_languages
            );
        ELSE
            RETURN json_build_object(
                'status', 'processing',
                'requested_at', processing_record.requested_at,
                'total_points', total_points,
                'completed_points', points_with_audio,
                'user_has_purchase', COALESCE(user_has_purchase, false),
                'narration_type', narration_type_param,
                'language_code', language_code_param,
                'message', 'Tour audio generation in progress...',
                'progress_percent', processing_record.progress_percent,
                'owned_languages', owned_languages
            );
        END IF;
    END IF;

    RETURN json_build_object(
        'status', 'not_started',
        'total_points', total_points,
        'completed_points', points_with_audio,
        'user_has_purchase', COALESCE(user_has_purchase, false),
        'narration_type', narration_type_param,
        'language_code', language_code_param,
        'message', 'Generation not started',
        'owned_languages', owned_languages
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public.invite_user_to_user_tour(
    sender_user_id UUID,
    tour_purchase_id UUID,
    recipient_email TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    purchase_record RECORD;
    recipient_user_id UUID;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);

    SELECT *
    INTO purchase_record
    FROM user_tour_purchases
    WHERE id = tour_purchase_id
      AND user_id = sender_user_id
      AND quantity_total > quantity_gifted
    LIMIT 1;

    IF purchase_record IS NULL THEN
        RAISE EXCEPTION 'Purchase not found or no remaining gift quantity';
    END IF;

    SELECT id INTO recipient_user_id
    FROM users
    WHERE lower(email) = lower(recipient_email)
    LIMIT 1;

    INSERT INTO user_tour_invitations (
        tour_purchase_id,
        sender_id,
        recipient_email,
        recipient_id,
        status
    ) VALUES (
        tour_purchase_id,
        sender_user_id,
        recipient_email,
        recipient_user_id,
        'pending'
    );

    UPDATE user_tour_purchases
    SET quantity_gifted = quantity_gifted + 1,
        updated_at = NOW()
    WHERE id = tour_purchase_id;

    IF recipient_user_id IS NOT NULL THEN
        INSERT INTO user_tour_purchases (
            user_id,
            user_tour_id,
            quantity_total,
            quantity_completed,
            quantity_gifted,
            source,
            narration_type,
            language_code
        )
        VALUES (
            recipient_user_id,
            purchase_record.user_tour_id,
            1,
            0,
            0,
            'gift',
            purchase_record.narration_type,
            purchase_record.language_code
        );

        UPDATE user_tour_invitations
        SET status = 'accepted',
            accepted_date = NOW(),
            updated_at = NOW()
        WHERE tour_purchase_id = tour_purchase_id
          AND sender_id = sender_user_id
          AND recipient_email = recipient_email
          AND status = 'pending';
    END IF;

    RETURN TRUE;

EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$function$;

CREATE OR REPLACE FUNCTION public.claim_pending_user_invitations(
    p_user_id UUID,
    p_email TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    normalized_email text := lower(trim(p_email));
    claimed_count integer := 0;
    invitation_record RECORD;
BEGIN
    IF p_user_id IS NULL THEN
        RETURN json_build_object('success', false, 'claimed', 0, 'message', 'user id is required');
    END IF;

    IF normalized_email IS NULL OR normalized_email = '' THEN
        RETURN json_build_object('success', false, 'claimed', 0, 'message', 'email is required');
    END IF;

    FOR invitation_record IN
        SELECT
            uti.id,
            uti.tour_purchase_id,
            utp.user_tour_id,
            utp.narration_type,
            utp.language_code
        FROM user_tour_invitations uti
        JOIN user_tour_purchases utp ON utp.id = uti.tour_purchase_id
        WHERE uti.status = 'pending'
          AND lower(uti.recipient_email) = normalized_email
        FOR UPDATE
    LOOP
        INSERT INTO user_tour_purchases (
            user_id,
            user_tour_id,
            quantity_total,
            quantity_completed,
            quantity_gifted,
            source,
            narration_type,
            language_code
        )
        VALUES (
            p_user_id,
            invitation_record.user_tour_id,
            1,
            0,
            0,
            'gift',
            invitation_record.narration_type,
            invitation_record.language_code
        );

        UPDATE user_tour_invitations
        SET status = 'accepted',
            recipient_id = p_user_id,
            accepted_date = NOW(),
            updated_at = NOW()
        WHERE id = invitation_record.id;

        claimed_count := claimed_count + 1;
    END LOOP;

    RETURN json_build_object(
        'success', true,
        'claimed', claimed_count
    );
EXCEPTION
    WHEN OTHERS THEN
        RETURN json_build_object(
            'success', false,
            'claimed', claimed_count,
            'message', SQLERRM
        );
END;
$function$;

CREATE OR REPLACE FUNCTION public.get_user_active_custom_tours(
    p_user_id UUID,
    p_language_code TEXT DEFAULT 'en'
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    result JSON;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);
    p_language_code := COALESCE(NULLIF(p_language_code, ''), 'en');

    SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
    INTO result
    FROM (
      SELECT
        utp.id AS purchase_id,
        utp.source,
        utp.purchase_date,
        utp.quantity_total,
        utp.quantity_completed,
        utp.quantity_gifted,
        utp.user_tour_id AS tour_id,
        ut.name AS tour_name,
        c.city,
        c.country,
        c.place_id,
        utp.language_code,
        ut.total_distance,
        ut.estimated_walking_time,
        ut.point_count,
        'custom' AS tour_type,
        fp.name AS first_point_name,
        fp.formatted_address AS first_point_address,
        fp.photos AS first_point_photos
      FROM user_tour_purchases utp
      JOIN user_tours ut ON ut.id = utp.user_tour_id
      JOIN cities c ON c.id = ut.city_id
      LEFT JOIN LATERAL (
        SELECT
          COALESCE(at.name, a.name) AS name,
          a.formatted_address,
          a.photos
        FROM user_tour_points utp2
        JOIN attractions a ON utp2.attraction_id = a.id
        LEFT JOIN attraction_translations at
          ON at.attraction_id = a.id
         AND at.language_code = p_language_code
        WHERE utp2.user_tour_id = ut.id
        ORDER BY COALESCE(utp2.point_order, utp2.global_index, 999999)
        LIMIT 1
      ) fp ON TRUE
      WHERE utp.user_id = p_user_id
    ) AS t;

    RETURN result;
END;
$function$;

-- ============================================================================
-- RLS for custom tour tables
-- ============================================================================
ALTER TABLE public.user_tours ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_tours_owner_select"
  ON public.user_tours
  FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);
CREATE POLICY "user_tours_owner_insert"
  ON public.user_tours
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);
CREATE POLICY "user_tours_owner_update"
  ON public.user_tours
  FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
CREATE POLICY "user_tours_owner_delete"
  ON public.user_tours
  FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);
CREATE POLICY "user_tours_service_role_all"
  ON public.user_tours
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

ALTER TABLE public.user_tour_points ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_tour_points_owner_select"
  ON public.user_tour_points
  FOR SELECT
  TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ));
CREATE POLICY "user_tour_points_owner_insert"
  ON public.user_tour_points
  FOR INSERT
  TO authenticated
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ));
CREATE POLICY "user_tour_points_owner_update"
  ON public.user_tour_points
  FOR UPDATE
  TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ));
CREATE POLICY "user_tour_points_owner_delete"
  ON public.user_tour_points
  FOR DELETE
  TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ));
CREATE POLICY "user_tour_points_service_role_all"
  ON public.user_tour_points
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

ALTER TABLE public.user_walking_paths ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_walking_paths_owner_select"
  ON public.user_walking_paths
  FOR SELECT
  TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ));
CREATE POLICY "user_walking_paths_owner_insert"
  ON public.user_walking_paths
  FOR INSERT
  TO authenticated
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ));
CREATE POLICY "user_walking_paths_owner_update"
  ON public.user_walking_paths
  FOR UPDATE
  TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ));
CREATE POLICY "user_walking_paths_owner_delete"
  ON public.user_walking_paths
  FOR DELETE
  TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.user_tours ut
    WHERE ut.id = user_tour_id
      AND ut.user_id = auth.uid()
  ));
CREATE POLICY "user_walking_paths_service_role_all"
  ON public.user_walking_paths
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

ALTER TABLE public.user_tour_purchases ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_tour_purchases_owner_select"
  ON public.user_tour_purchases
  FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);
CREATE POLICY "user_tour_purchases_owner_update"
  ON public.user_tour_purchases
  FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
CREATE POLICY "user_tour_purchases_owner_delete"
  ON public.user_tour_purchases
  FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);
CREATE POLICY "user_tour_purchases_service_role_all"
  ON public.user_tour_purchases
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

ALTER TABLE public.user_tour_invitations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_tour_invitations_sender_recipient_select"
  ON public.user_tour_invitations
  FOR SELECT
  TO authenticated
  USING (
    auth.uid() = sender_id
    OR auth.uid() = recipient_id
  );
CREATE POLICY "user_tour_invitations_service_role_all"
  ON public.user_tour_invitations
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

ALTER TABLE public.processing_user_tour_generation ENABLE ROW LEVEL SECURITY;
CREATE POLICY "processing_user_tour_generation_service_role_all"
  ON public.processing_user_tour_generation
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- =====================================================================
-- Guided tours map (with attraction types, tolerant jsonb conversion)
-- =====================================================================
CREATE OR REPLACE FUNCTION public.get_city_tours_map(
    city_id_param UUID,
    language_code_param TEXT DEFAULT 'en'
)
RETURNS TABLE(
    city_id UUID,
    city_name VARCHAR,
    tour_id UUID,
    tour_order INTEGER,
    tour_name VARCHAR,
    total_distance INTEGER,
    estimated_walking_time INTEGER,
    point_count INTEGER,
    cover_photo JSONB,
    points JSONB
) AS $function$
BEGIN
  RETURN QUERY
  WITH tour_points_expanded AS (
    SELECT
      gt.id as tour_id,
      gt.city_id,
      COALESCE(gtt.tour_name, gt.tour_name) as tour_name,
      gt.tour_id as tour_order,
      gt.total_distance,
      gt.estimated_walking_time,
      gt.point_count,
      tp.point_order,
      tp.global_index,
      ROW_NUMBER() OVER (PARTITION BY gt.id ORDER BY tp.point_order) as point_rank,
      a.id as attraction_id,
      COALESCE(att.name, a.name) as attraction_name,
      a.lat,
      a.lng,
      a.photos,
      COALESCE(to_jsonb(a.types), '[]'::jsonb) AS types_json,
      CASE
        WHEN a.photos IS NOT NULL
             AND jsonb_typeof(a.photos) = 'array'
             AND jsonb_array_length(a.photos) > 0
        THEN jsonb_build_object(
          'photo_reference', a.photos->0->>'photo_reference',
          'height', NULLIF(a.photos->0->>'height', '')::int,
          'width', NULLIF(a.photos->0->>'width', '')::int
        )
        ELSE NULL
      END AS first_photo
    FROM guided_tours gt
    JOIN tour_points tp ON tp.tour_id = gt.id
    JOIN attractions a ON a.id = tp.attraction_id
    LEFT JOIN guided_tour_translations gtt
      ON gt.id = gtt.tour_id AND gtt.language_code = language_code_param
    LEFT JOIN attraction_translations att
      ON a.id = att.attraction_id AND att.language_code = language_code_param
    WHERE gt.city_id = city_id_param
  ),
  cover_photos AS (
    SELECT DISTINCT ON (tpe.tour_id)
      tpe.tour_id,
      CASE
        WHEN tpe.photos IS NOT NULL
             AND jsonb_typeof(tpe.photos) = 'array'
             AND jsonb_array_length(tpe.photos) > 0
        THEN jsonb_build_object(
          'photo_reference', tpe.photos->0->>'photo_reference',
          'height', NULLIF(tpe.photos->0->>'height', '')::int,
          'width', NULLIF(tpe.photos->0->>'width', '')::int
        )
        ELSE NULL
      END AS cover_photo
    FROM tour_points_expanded tpe
    ORDER BY tpe.tour_id, tpe.point_rank
  )
  SELECT
    t.city_id,
    COALESCE(ct.city, c.city) as city_name,
    t.tour_id,
    t.tour_order,
    t.tour_name,
    t.total_distance,
    t.estimated_walking_time,
    t.point_count,
    cp.cover_photo,
    jsonb_agg(
      jsonb_build_object(
        'id', t.attraction_id,
        'name', t.attraction_name,
        'lat', t.lat::numeric,
        'lng', t.lng::numeric,
        'point_order', t.point_order,
        'global_index', t.global_index,
        'types', t.types_json,
        'photo', t.first_photo
      )
      ORDER BY t.point_order
    ) as points
  FROM tour_points_expanded t
  JOIN cities c ON c.id = t.city_id
  LEFT JOIN city_translations ct
    ON c.id = ct.city_id AND ct.language_code = language_code_param
  LEFT JOIN cover_photos cp ON cp.tour_id = t.tour_id
  GROUP BY
    t.city_id,
    c.city,
    ct.city,
    t.tour_id,
    t.tour_order,
    t.tour_name,
    t.total_distance,
    t.estimated_walking_time,
    t.point_count,
    cp.cover_photo;
END;
$function$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION public.get_city_tours_map IS 'Returns city tours with map points (including attraction types) and translations based on language_code';

-- =====================================================================
-- Create a custom user tour and its ordered points
-- =====================================================================
CREATE OR REPLACE FUNCTION public.upsert_user_tour(
    p_user_id UUID,
    p_city_id UUID,
    p_name TEXT DEFAULT 'Custom tour',
    p_attraction_ids UUID[] DEFAULT '{}',
    p_cover_photo JSONB DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_user_tour_id UUID;
    v_point_count INTEGER;
BEGIN
    PERFORM set_config('request.jwt.claim.role', 'service_role', true);

    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'user id is required';
    END IF;

    IF p_city_id IS NULL THEN
        RAISE EXCEPTION 'city id is required';
    END IF;

    IF p_attraction_ids IS NULL OR array_length(p_attraction_ids, 1) IS NULL THEN
        RAISE EXCEPTION 'attraction_ids must be provided';
    END IF;

    v_point_count := array_length(p_attraction_ids, 1);

    INSERT INTO user_tours (
        user_id,
        city_id,
        name,
        point_count,
        cover_photo,
        total_distance,
        estimated_walking_time
    )
    VALUES (
        p_user_id,
        p_city_id,
        COALESCE(NULLIF(p_name, ''), 'Custom tour'),
        v_point_count,
        p_cover_photo,
        NULL,
        NULL
    )
    RETURNING id INTO v_user_tour_id;

    -- Insert ordered points
    FOR i IN 1..v_point_count LOOP
        INSERT INTO user_tour_points (
            user_tour_id,
            attraction_id,
            point_order,
            global_index
        ) VALUES (
            v_user_tour_id,
            p_attraction_ids[i],
            i,
            i
        );
    END LOOP;

    RETURN v_user_tour_id;
END;
$function$;

-- =====================================================================
