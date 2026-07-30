-- profiles: display name shown in shared listings instead of raw emails.
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;

create policy "profiles are visible to authenticated users"
  on public.profiles for select to authenticated using (true);
create policy "users insert their own profile"
  on public.profiles for insert to authenticated with check (id = auth.uid());
create policy "users update their own profile"
  on public.profiles for update to authenticated using (id = auth.uid());

-- categories: global shared taxonomy, editable only by whoever created each one.
create table public.categories (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  color text,
  position int not null default 0,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);
alter table public.categories enable row level security;

create policy "categories are visible to authenticated users"
  on public.categories for select to authenticated using (true);
create policy "authenticated users create categories"
  on public.categories for insert to authenticated with check (created_by = auth.uid());
create policy "creators update their categories"
  on public.categories for update to authenticated using (created_by = auth.uid());
create policy "creators delete their categories"
  on public.categories for delete to authenticated using (created_by = auth.uid());

-- sounds: shared global library, editable only by the owner.
create table public.sounds (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  category_id uuid references public.categories(id) on delete set null,
  name text not null,
  sha256 text not null,
  storage_path text not null,
  source_filename text not null,
  duration_frames int not null,
  orig_samplerate int not null,
  orig_channels int not null,
  gain_db real not null default 0,
  trim_start_frames int not null default 0,
  trim_end_frames int,
  loop boolean not null default false,
  color text,
  tags text[],
  created_at timestamptz not null default now(),
  unique (owner_id, sha256)
);
alter table public.sounds enable row level security;

create policy "sounds are visible to authenticated users"
  on public.sounds for select to authenticated using (true);
create policy "owners insert their sounds"
  on public.sounds for insert to authenticated with check (owner_id = auth.uid());
create policy "owners update their sounds"
  on public.sounds for update to authenticated using (owner_id = auth.uid());
create policy "owners delete their sounds"
  on public.sounds for delete to authenticated using (owner_id = auth.uid());

-- storage: content-addressed PCM blobs, immutable once written.
insert into storage.buckets (id, name, public)
  values ('sounds', 'sounds', false)
  on conflict (id) do nothing;

create policy "authenticated read sound blobs"
  on storage.objects for select to authenticated
  using (bucket_id = 'sounds');
create policy "authenticated upload sound blobs"
  on storage.objects for insert to authenticated
  with check (bucket_id = 'sounds');
