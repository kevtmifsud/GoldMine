-- 031_update_alt_data_type_check.sql
-- Expand alt_data data_type check constraint for new signal types.

ALTER TABLE alt_data DROP CONSTRAINT IF EXISTS alt_data_data_type_check;

ALTER TABLE alt_data ADD CONSTRAINT alt_data_data_type_check
  CHECK (data_type IN (
    'credit_card', 'web_traffic', 'app_downloads',
    'google_trends', 'email_receipts', 'medical_claims',
    'credit_card_sss_yoy', 'credit_card_txn_yoy', 'credit_card_spv_yoy',
    'foot_traffic_yoy', 'app_downloads_yoy', 'web_traffic_yoy',
    'reservations_yoy', 'job_postings_yoy'
  ));
