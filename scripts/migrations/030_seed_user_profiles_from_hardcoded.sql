-- 030_seed_user_profiles_from_hardcoded.sql
-- Insert demo users from backend/app/auth/users.py into user_profiles.
-- Uses display_name uniqueness to be idempotent.

-- Drop FK to auth.users since we use app-level auth, not Supabase auth
ALTER TABLE user_profiles
  DROP CONSTRAINT IF EXISTS user_profiles_user_id_fkey;

-- Add unique constraint on display_name if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'user_profiles_display_name_unique'
  ) THEN
    ALTER TABLE user_profiles
      ADD CONSTRAINT user_profiles_display_name_unique
      UNIQUE (display_name);
  END IF;
END $$;

-- Insert demo users
INSERT INTO user_profiles
  (user_id, display_name, role, is_admin, created_at, updated_at)
VALUES
  (gen_random_uuid(), 'Alice Chen', 'analyst', false, NOW(), NOW()),
  (gen_random_uuid(), 'Bob Martinez', 'analyst', false, NOW(), NOW()),
  (gen_random_uuid(), 'Carol Wu', 'analyst', false, NOW(), NOW())
ON CONFLICT (display_name) DO NOTHING;
