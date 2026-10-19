-- Issue 11 : recherche sémantique (pgvector)
-- À exécuter une fois dans Supabase → SQL Editor

create index if not exists candidats_embedding_idx
    on public.candidats
    using hnsw (embedding vector_cosine_ops);

-- Candidats analysés classés par similarité cosinus avec la requête, avec filtre d'expérience optionnel
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

-- Appelée uniquement côté serveur, avec la clé service_role
revoke execute on function public.match_candidats(vector, int, numeric, numeric, boolean)
    from public, anon, authenticated;
grant execute on function public.match_candidats(vector, int, numeric, numeric, boolean)
    to service_role;
