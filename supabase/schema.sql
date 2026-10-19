-- Schéma CVthèque IA
-- À exécuter dans Supabase → SQL Editor
-- Installation neuve : ce fichier suffit et peut être relancé sans risque.
-- Les fichiers de migrations/ ne servent qu'à mettre à jour une base créée avec une version antérieure.

-- 1. Extension pgvector
create extension if not exists vector;

-- 2. Table candidats
create table if not exists public.candidats (
    id uuid primary key default gen_random_uuid(),
    nom text,
    prenom text,
    email text,
    telephone text,
    poste text,
    experience_annees numeric,
    competences text[] default '{}',
    technologies text[] default '{}',
    formations text[] default '{}',
    certifications text[],
    langues text[] default '{}',
    incertitudes text[] default '{}',
    texte_brut text,
    chemin_fichier text,
    statut text not null default 'importe'
        constraint candidats_statut_check check (statut in ('importe', 'analyse', 'erreur')),
    embedding vector(384),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists candidats_statut_idx on public.candidats (statut);

-- 3. Table appels d'offres
create table if not exists public.appels_offres (
    id uuid primary key default gen_random_uuid(),
    titre text not null,
    poste text,
    contexte text,
    responsabilites text[],
    competences_obligatoires text[] default '{}',
    competences_souhaitees text[] default '{}',
    experience_requise text,
    experience_min_annees numeric,
    technologies text[] default '{}',
    contraintes text[],
    profil_ideal text,
    incertitudes text[] default '{}',
    texte_brut text,
    chemin_fichier text,
    embedding vector(384),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists appels_offres_created_at_idx on public.appels_offres (created_at desc);

-- 4. Index pour recherche vectorielle (cosine) — HNSW (ok même table vide)
create index if not exists candidats_embedding_idx
    on public.candidats
    using hnsw (embedding vector_cosine_ops);

create index if not exists appels_offres_embedding_idx
    on public.appels_offres
    using hnsw (embedding vector_cosine_ops);

-- 5. Row Level Security : aucune policy => accès refusé aux clés anon/authenticated.
--    L'app utilise la clé service_role, qui contourne la RLS.
alter table public.candidats enable row level security;
alter table public.appels_offres enable row level security;

-- 6. Buckets Storage privés : CV et fichiers d'appels d'offres
insert into storage.buckets (id, name, public)
values ('cvs', 'cvs', false), ('appels-offres', 'appels-offres', false)
on conflict (id) do nothing;

-- Politique : accès uniquement via service_role (pas de policy publique)
-- Les uploads/lectures se font côté serveur Streamlit avec la clé service_role.

-- 7. Recherche sémantique : candidats analysés classés par similarité cosinus
create or replace function public.match_candidats(
    query_embedding vector(384),
    match_count int default 20,
    experience_min numeric default null,
    experience_max numeric default null,
    include_unknown_experience boolean default false
)
returns table (id uuid, similarity double precision)
language sql
stable
set search_path = public, extensions
as $$
    select c.id, 1 - (c.embedding <=> query_embedding) as similarity
    from public.candidats c
    where c.embedding is not null
      and c.statut = 'analyse'
      and (
          (experience_min is null and experience_max is null)
          or (c.experience_annees is null and include_unknown_experience)
          or (
              (experience_min is null or c.experience_annees >= experience_min)
              and (experience_max is null or c.experience_annees <= experience_max)
          )
      )
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

revoke execute on function public.match_candidats(vector, int, numeric, numeric, boolean)
    from public, anon, authenticated;
grant execute on function public.match_candidats(vector, int, numeric, numeric, boolean)
    to service_role;
