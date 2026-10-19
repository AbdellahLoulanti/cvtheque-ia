-- Issue 13 : import et analyse IA des appels d'offres
-- À exécuter une fois dans Supabase → SQL Editor

alter table public.appels_offres add column if not exists poste text;
alter table public.appels_offres add column if not exists responsabilites text[];
alter table public.appels_offres add column if not exists experience_min_annees numeric;
alter table public.appels_offres add column if not exists incertitudes text[] default '{}';
alter table public.appels_offres add column if not exists texte_brut text;
alter table public.appels_offres add column if not exists chemin_fichier text;

-- contraintes : texte libre -> liste d'éléments courts (lieu, durée, démarrage…)
do $$
begin
    if exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'appels_offres'
          and column_name = 'contraintes' and data_type = 'text'
    ) then
        alter table public.appels_offres
            alter column contraintes type text[]
            using case when contraintes is null then null else array[contraintes] end;
    end if;
end $$;

create index if not exists appels_offres_created_at_idx on public.appels_offres (created_at desc);

-- Bucket Storage privé des fichiers d'AO (accès via la clé service_role uniquement)
insert into storage.buckets (id, name, public)
values ('appels-offres', 'appels-offres', false)
on conflict (id) do nothing;
