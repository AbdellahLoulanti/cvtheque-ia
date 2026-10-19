-- Issue 5 : analyse IA des CV
-- À exécuter une fois dans Supabase → SQL Editor (base créée avec la version précédente de schema.sql)

alter table public.candidats add column if not exists certifications text[];
alter table public.candidats add column if not exists statut text not null default 'importe';

alter table public.candidats drop constraint if exists candidats_statut_check;
alter table public.candidats
    add constraint candidats_statut_check check (statut in ('importe', 'analyse', 'erreur'));

create index if not exists candidats_statut_idx on public.candidats (statut);
