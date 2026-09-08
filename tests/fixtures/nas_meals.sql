-- NAS PostgreSQL 17.11 schema-only snapshot, 2026-09-08. No business data.
CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;

CREATE TABLE public.meals (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    pair_id uuid,
    user_name character varying(100),
    user_role character varying(50),
    name character varying(255) NOT NULL,
    calories numeric(10,2) DEFAULT 0 NOT NULL,
    protein numeric(10,2) DEFAULT 0 NOT NULL,
    carbs numeric(10,2) DEFAULT 0 NOT NULL,
    fat numeric(10,2) DEFAULT 0 NOT NULL,
    original_calories numeric(10,2),
    original_protein numeric(10,2),
    original_carbs numeric(10,2),
    original_fat numeric(10,2),
    base_calories numeric(10,2),
    base_protein numeric(10,2),
    base_carbs numeric(10,2),
    base_fat numeric(10,2),
    dishes jsonb DEFAULT '[]'::jsonb NOT NULL,
    original_dishes jsonb DEFAULT '[]'::jsonb NOT NULL,
    base_dishes jsonb DEFAULT '[]'::jsonb NOT NULL,
    image_url text,
    hint text,
    source character varying(30) DEFAULT 'manual'::character varying NOT NULL,
    portion_ratio numeric(8,4) DEFAULT 1 NOT NULL,
    share_ratio numeric(8,4) DEFAULT 1 NOT NULL,
    share_mode character varying(30) DEFAULT 'solo'::character varying NOT NULL,
    shared_meal_id uuid,
    meal_date date NOT NULL,
    meal_time time without time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT meals_base_dishes_array CHECK ((jsonb_typeof(base_dishes) = 'array'::text)),
    CONSTRAINT meals_calories_nonnegative CHECK ((calories >= (0)::numeric)),
    CONSTRAINT meals_carbs_nonnegative CHECK ((carbs >= (0)::numeric)),
    CONSTRAINT meals_dishes_array CHECK ((jsonb_typeof(dishes) = 'array'::text)),
    CONSTRAINT meals_fat_nonnegative CHECK ((fat >= (0)::numeric)),
    CONSTRAINT meals_original_dishes_array CHECK ((jsonb_typeof(original_dishes) = 'array'::text)),
    CONSTRAINT meals_portion_ratio_positive CHECK ((portion_ratio > (0)::numeric)),
    CONSTRAINT meals_protein_nonnegative CHECK ((protein >= (0)::numeric)),
    CONSTRAINT meals_share_ratio_valid CHECK (((share_ratio >= (0)::numeric) AND (share_ratio <= (1)::numeric)))
);


--
-- Name: meals meals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meals
    ADD CONSTRAINT meals_pkey PRIMARY KEY (id);


--
-- Name: idx_meals_pair_date_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_meals_pair_date_time ON public.meals USING btree (pair_id, meal_date, meal_time);


--
-- Name: idx_meals_shared_meal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_meals_shared_meal ON public.meals USING btree (shared_meal_id) WHERE (shared_meal_id IS NOT NULL);


--
-- Name: idx_meals_user_date_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_meals_user_date_time ON public.meals USING btree (user_id, meal_date, meal_time DESC);


--
-- Name: meals trg_meals_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_meals_updated_at BEFORE UPDATE ON public.meals FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: meals meals_pair_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meals
    ADD CONSTRAINT meals_pair_id_fkey FOREIGN KEY (pair_id) REFERENCES public.pairs(id) ON DELETE SET NULL;


--
-- Name: meals meals_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meals
    ADD CONSTRAINT meals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
