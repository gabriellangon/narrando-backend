-- public.attraction_translations definition

-- Drop table

-- DROP TABLE public.attraction_translations;

CREATE TABLE public.attraction_translations (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	attraction_id uuid NOT NULL,
	language_code varchar(5) NOT NULL,
	"name" varchar(255) NOT NULL,
	ai_description text NULL,
	audio_url jsonb DEFAULT '{}'::jsonb NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT attraction_translations_attraction_id_language_code_key UNIQUE (attraction_id, language_code),
	CONSTRAINT attraction_translations_pkey PRIMARY KEY (id),
	CONSTRAINT attraction_translations_attraction_id_fkey FOREIGN KEY (attraction_id) REFERENCES public.attractions(id) ON DELETE CASCADE
);
CREATE INDEX idx_attraction_translations_attraction_id ON public.attraction_translations USING btree (attraction_id);
CREATE INDEX idx_attraction_translations_language_code ON public.attraction_translations USING btree (language_code);

-- Table Triggers

create trigger update_attraction_translations_updated_at before
update
    on
    public.attraction_translations for each row execute function update_updated_at_column();


-- public.attractions definition

-- Drop table

-- DROP TABLE public.attractions;

CREATE TABLE public.attractions (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	city_id uuid NULL,
	"name" varchar(200) NOT NULL,
	formatted_address text NULL,
	lat numeric(10, 8) NOT NULL,
	lng numeric(11, 8) NOT NULL,
	route_index int4 NOT NULL,
	distance_from_previous int4 DEFAULT 0 NULL,
	walking_time_from_previous int4 DEFAULT 0,
	ai_evaluation_timestamp timestamptz NULL,
	place_id varchar(200) NULL,
	rating numeric(2, 1) NULL,
	"types" jsonb NULL,
	photos jsonb NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamp DEFAULT now() NULL,
	audio_url jsonb DEFAULT '{}'::jsonb NULL,
	ai_description jsonb DEFAULT '{}'::jsonb NULL,
	CONSTRAINT attractions_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_attractions_city_id ON public.attractions USING btree (city_id);
CREATE INDEX idx_attractions_location ON public.attractions USING btree (lat, lng);
CREATE INDEX idx_attractions_place_id ON public.attractions USING btree (place_id);
CREATE INDEX idx_attractions_route_index ON public.attractions USING btree (route_index);


-- public.attractions foreign keys

ALTER TABLE public.attractions ADD CONSTRAINT attractions_city_id_fkey FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE CASCADE;


-- public.audio_samples definition

-- Drop table

-- DROP TABLE public.audio_samples;

CREATE TABLE public.audio_samples (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	language_code varchar(5) NOT NULL,
	audio_url jsonb DEFAULT '{}'::jsonb NOT NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT audio_samples_language_code_key UNIQUE (language_code),
	CONSTRAINT audio_samples_pkey PRIMARY KEY (id)
);

-- public.cities definition

-- Drop table

-- DROP TABLE public.cities;

CREATE TABLE public.cities (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	city varchar(100) NOT NULL,
	country varchar(100) NOT NULL,
	country_iso_code varchar(2) NULL,
	place_id varchar(200) NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	audio_url text NULL,
	CONSTRAINT cities_pkey PRIMARY KEY (id),
	CONSTRAINT unique_city_country UNIQUE (city, country)
);
CREATE INDEX idx_cities_city_country ON public.cities USING btree (city, country);
CREATE INDEX idx_cities_created_at ON public.cities USING btree (created_at);

-- Table Triggers

create trigger update_cities_updated_at before
update
    on
    public.cities for each row execute function update_updated_at_column();

 -- public.city_translations definition

-- Drop table

-- DROP TABLE public.city_translations;

CREATE TABLE public.city_translations (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	city_id uuid NOT NULL,
	language_code varchar(5) NOT NULL,
	city varchar(255) NOT NULL,
	country varchar(255) NOT NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT city_translations_city_id_language_code_key UNIQUE (city_id, language_code),
	CONSTRAINT city_translations_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_city_translations_city_id ON public.city_translations USING btree (city_id);
CREATE INDEX idx_city_translations_language_code ON public.city_translations USING btree (language_code);

-- Table Triggers

create trigger update_city_translations_updated_at before
update
    on
    public.city_translations for each row execute function update_updated_at_column();


-- public.city_translations foreign keys

ALTER TABLE public.city_translations ADD CONSTRAINT city_translations_city_id_fkey FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE CASCADE;

-- public.guided_tour_translations definition

-- Drop table

-- DROP TABLE public.guided_tour_translations;

CREATE TABLE public.guided_tour_translations (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	tour_id uuid NOT NULL,
	language_code varchar(5) NOT NULL,
	tour_name varchar(255) NOT NULL,
	description text NULL,
	audio_url jsonb DEFAULT '{}'::jsonb NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT guided_tour_translations_pkey PRIMARY KEY (id),
	CONSTRAINT guided_tour_translations_tour_id_language_code_key UNIQUE (tour_id, language_code)
);
CREATE INDEX idx_guided_tour_translations_language_code ON public.guided_tour_translations USING btree (language_code);
CREATE INDEX idx_guided_tour_translations_tour_id ON public.guided_tour_translations USING btree (tour_id);

-- Table Triggers

create trigger update_guided_tour_translations_updated_at before
update
    on
    public.guided_tour_translations for each row execute function update_updated_at_column();


-- public.guided_tour_translations foreign keys

ALTER TABLE public.guided_tour_translations ADD CONSTRAINT guided_tour_translations_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.guided_tours(id) ON DELETE CASCADE;

-- public.guided_tours definition

-- Drop table

-- DROP TABLE public.guided_tours;

CREATE TABLE public.guided_tours (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	city_id uuid NULL,
	tour_id int4 NOT NULL,
	tour_name varchar(100) NOT NULL,
	max_participants int4 DEFAULT 3 NULL,
	total_distance int4 NULL,
	estimated_walking_time int4 NULL,
	point_count int4 NULL,
	start_point varchar(200) NULL,
	end_point varchar(200) NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	audio_url text NULL,
	description text NULL,
	CONSTRAINT guided_tours_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_guided_tours_city_id ON public.guided_tours USING btree (city_id);
CREATE INDEX idx_guided_tours_tour_id ON public.guided_tours USING btree (tour_id);

-- Table Triggers

create trigger update_guided_tours_updated_at before
update
    on
    public.guided_tours for each row execute function update_updated_at_column();


-- public.guided_tours foreign keys

ALTER TABLE public.guided_tours ADD CONSTRAINT guided_tours_city_id_fkey FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE CASCADE;

-- public.processing_city definition

-- Drop table

-- DROP TABLE public.processing_city;

CREATE TABLE public.processing_city (
	place_id varchar(200) NOT NULL,
	status varchar(50) DEFAULT 'processing'::character varying NOT NULL,
	requested_at timestamptz DEFAULT now() NULL,
	last_checked_at timestamptz DEFAULT now() NULL,
	error_message text NULL,
	CONSTRAINT processing_city_pkey PRIMARY KEY (place_id)
);
CREATE INDEX idx_processing_city_place_id_status ON public.processing_city USING btree (place_id, status);
CREATE INDEX idx_processing_city_requested_at ON public.processing_city USING btree (requested_at);

-- public.processing_tour_generation definition

-- Drop table

-- DROP TABLE public.processing_tour_generation;

CREATE TABLE public.processing_tour_generation (
	tour_id uuid NOT NULL,
	status varchar(50) DEFAULT 'processing'::character varying NOT NULL,
	requested_at timestamptz DEFAULT now() NULL,
	last_checked_at timestamptz DEFAULT now() NULL,
	narration_type text DEFAULT 'standard'::text NOT NULL,
	error_message text NULL,
	language_code varchar(5) DEFAULT 'en'::character varying NOT NULL,
	CONSTRAINT processing_tour_generation_pkey PRIMARY KEY (tour_id, narration_type)
);
CREATE INDEX idx_processing_tour_gen_type ON public.processing_tour_generation USING btree (tour_id, narration_type, status);
CREATE UNIQUE INDEX idx_processing_tour_generation_key ON public.processing_tour_generation USING btree (tour_id, narration_type, language_code);
CREATE INDEX idx_processing_tour_generation_requested_at ON public.processing_tour_generation USING btree (requested_at);
CREATE INDEX idx_processing_tour_generation_tour_id_status ON public.processing_tour_generation USING btree (tour_id, status);

-- public.processing_tour_preview definition

-- Drop table

-- DROP TABLE public.processing_tour_preview;

CREATE TABLE public.processing_tour_preview (
	tour_id uuid NOT NULL,
	status varchar(50) DEFAULT 'processing'::character varying NOT NULL,
	requested_at timestamptz DEFAULT now() NULL,
	last_checked_at timestamptz DEFAULT now() NULL,
	CONSTRAINT processing_tour_preview_pkey PRIMARY KEY (tour_id)
);
CREATE INDEX idx_processing_tour_preview_requested_at ON public.processing_tour_preview USING btree (requested_at);

-- public.test_first_call definition

-- Drop table

-- DROP TABLE public.test_first_call;

CREATE TABLE public.test_first_call (
	place_id varchar(200) NOT NULL,
	created_at timestamptz DEFAULT now() NULL,
	CONSTRAINT test_first_call_pkey PRIMARY KEY (place_id)
);

-- public.tour_invitations definition

-- Drop table

-- DROP TABLE public.tour_invitations;

CREATE TABLE public.tour_invitations (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	sender_id uuid NULL,
	recipient_email varchar(255) NOT NULL,
	tour_purchase_id uuid NULL,
	status varchar(50) DEFAULT 'pending'::character varying NULL,
	invitation_date timestamptz DEFAULT now() NULL,
	accepted_date timestamptz NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT tour_invitations_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_tour_invitations_recipient_email ON public.tour_invitations USING btree (recipient_email);
CREATE INDEX idx_tour_invitations_sender_id ON public.tour_invitations USING btree (sender_id);

-- Table Triggers

create trigger update_tour_invitations_updated_at before
update
    on
    public.tour_invitations for each row execute function update_updated_at_column();


-- public.tour_invitations foreign keys

ALTER TABLE public.tour_invitations ADD CONSTRAINT tour_invitations_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.tour_invitations ADD CONSTRAINT tour_invitations_tour_purchase_id_fkey FOREIGN KEY (tour_purchase_id) REFERENCES public.tour_purchases(id) ON DELETE CASCADE;

-- public.tour_participants definition

-- Drop table

-- DROP TABLE public.tour_participants;

CREATE TABLE public.tour_participants (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	user_id uuid NULL,
	tour_purchase_id uuid NULL,
	invitation_id uuid NULL,
	join_date timestamptz DEFAULT now() NULL,
	start_date timestamptz NULL,
	completion_date timestamptz NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT tour_participants_pkey PRIMARY KEY (id),
	CONSTRAINT unique_user_purchase UNIQUE (user_id, tour_purchase_id)
);
CREATE INDEX idx_tour_participants_tour_purchase_id ON public.tour_participants USING btree (tour_purchase_id);
CREATE INDEX idx_tour_participants_user_id ON public.tour_participants USING btree (user_id);


-- public.tour_participants foreign keys

ALTER TABLE public.tour_participants ADD CONSTRAINT tour_participants_invitation_id_fkey FOREIGN KEY (invitation_id) REFERENCES public.tour_invitations(id) ON DELETE SET NULL;
ALTER TABLE public.tour_participants ADD CONSTRAINT tour_participants_tour_purchase_id_fkey FOREIGN KEY (tour_purchase_id) REFERENCES public.tour_purchases(id) ON DELETE CASCADE;
ALTER TABLE public.tour_participants ADD CONSTRAINT tour_participants_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- public.tour_points definition

-- Drop table

-- DROP TABLE public.tour_points;

CREATE TABLE public.tour_points (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	tour_id uuid NULL,
	attraction_id uuid NULL,
	point_order int4 NOT NULL,
	global_index int4 NOT NULL,
	created_at timestamptz DEFAULT now() NULL,
	CONSTRAINT tour_points_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_tour_points_attraction_id ON public.tour_points USING btree (attraction_id);
CREATE INDEX idx_tour_points_order ON public.tour_points USING btree (point_order);
CREATE INDEX idx_tour_points_tour_id ON public.tour_points USING btree (tour_id);


-- public.tour_points foreign keys

ALTER TABLE public.tour_points ADD CONSTRAINT tour_points_attraction_id_fkey FOREIGN KEY (attraction_id) REFERENCES public.attractions(id) ON DELETE CASCADE;
ALTER TABLE public.tour_points ADD CONSTRAINT tour_points_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.guided_tours(id) ON DELETE CASCADE;

-- public.tour_purchases definition

-- Drop table

-- DROP TABLE public.tour_purchases;

CREATE TABLE public.tour_purchases (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	user_id uuid NULL,
	tour_id uuid NULL,
	purchase_date timestamptz DEFAULT now() NULL,
	expiration_date timestamptz NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	quantity_total int4 DEFAULT 3 NULL,
	quantity_completed int4 DEFAULT 0 NULL,
	quantity_gifted int4 DEFAULT 0 NULL,
	"source" varchar(20) DEFAULT 'purchase'::character varying NULL,
	narration_type text DEFAULT 'standard'::text NOT NULL,
	language_code varchar(5) DEFAULT 'en'::character varying NOT NULL,
	CONSTRAINT tour_purchases_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_tour_purchases_tour_id ON public.tour_purchases USING btree (tour_id);
CREATE INDEX idx_tour_purchases_user_id ON public.tour_purchases USING btree (user_id);
CREATE INDEX idx_tour_purchases_user_tour_type ON public.tour_purchases USING btree (user_id, tour_id, narration_type);

-- Table Triggers

create trigger update_tour_purchases_updated_at before
update
    on
    public.tour_purchases for each row execute function update_updated_at_column();


-- public.tour_purchases foreign keys

ALTER TABLE public.tour_purchases ADD CONSTRAINT tour_purchases_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.guided_tours(id) ON DELETE CASCADE;
ALTER TABLE public.tour_purchases ADD CONSTRAINT tour_purchases_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- public.users definition

-- Drop table

-- DROP TABLE public.users;

CREATE TABLE public.users (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	email varchar(255) NOT NULL,
	first_name varchar(100) NULL,
	last_name varchar(100) NULL,
	fcm_token text NULL,
	last_login timestamptz NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	credits int4 DEFAULT 0 NOT NULL,
	CONSTRAINT users_email_key UNIQUE (email),
	CONSTRAINT users_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_users_email ON public.users USING btree (email);
CREATE INDEX idx_users_preview_credits ON public.users USING btree (credits);

-- Table Triggers

create trigger update_users_updated_at before
update
    on
    public.users for each row execute function update_updated_at_column();

-- public.walking_paths definition

-- Drop table

-- DROP TABLE public.walking_paths;

CREATE TABLE public.walking_paths (
	id uuid DEFAULT uuid_generate_v4() NOT NULL,
	tour_id uuid NULL,
	from_attraction_id uuid NULL,
	to_attraction_id uuid NULL,
	path_coordinates jsonb NULL,
	created_at timestamptz DEFAULT now() NULL,
	CONSTRAINT walking_paths_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_walking_paths_attractions ON public.walking_paths USING btree (from_attraction_id, to_attraction_id);
CREATE INDEX idx_walking_paths_tour_id ON public.walking_paths USING btree (tour_id);


-- public.walking_paths foreign keys

ALTER TABLE public.walking_paths ADD CONSTRAINT walking_paths_from_attraction_id_fkey FOREIGN KEY (from_attraction_id) REFERENCES public.attractions(id) ON DELETE CASCADE;
ALTER TABLE public.walking_paths ADD CONSTRAINT walking_paths_to_attraction_id_fkey FOREIGN KEY (to_attraction_id) REFERENCES public.attractions(id) ON DELETE CASCADE;
ALTER TABLE public.walking_paths ADD CONSTRAINT walking_paths_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.guided_tours(id) ON DELETE CASCADE;

