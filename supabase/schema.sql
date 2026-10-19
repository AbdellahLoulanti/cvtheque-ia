-- Schéma CVthèque IA
-- À exécuter dans Supabase → SQL Editor

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
    langues text[] default '{}',
    incertitudes text[] default '{}',
    texte_brut text,
    chemin_fichier text,
    embedding vector(384),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 3. Table appels d'offres
create table if not exists public.appels_offres (
    id uuid primary key default gen_random_uuid(),
    titre text not null,
    contexte text,
    competences_obligatoires text[] default '{}',
    competences_souhaitees text[] default '{}',
    experience_requise text,
    technologies text[] default '{}',
    contraintes text,
    profil_ideal text,
    embedding vector(384),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

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

-- 6. Bucket Storage privé "cvs"
insert into storage.buckets (id, name, public)
values ('cvs', 'cvs', false)
on conflict (id) do nothing;

-- Politique : accès uniquement via service_role (pas de policy publique)
-- Les uploads/lectures se font côté serveur Streamlit avec la clé service_role.
