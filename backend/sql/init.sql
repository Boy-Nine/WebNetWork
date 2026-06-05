CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  phone VARCHAR(20) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  nickname VARCHAR(64),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS capture_records (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  page_title VARCHAR(500),
  html_content TEXT,
  xhr_data JSONB NOT NULL DEFAULT '[]'::jsonb,
  parsed_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  capture_time TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS capture_sessions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  page_url TEXT NOT NULL,
  page_title VARCHAR(500),
  html_snapshot TEXT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  captured_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS captured_apis (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id INTEGER REFERENCES capture_sessions(id) ON DELETE CASCADE,
  method VARCHAR(12) NOT NULL,
  url TEXT NOT NULL,
  request_headers JSONB,
  response_headers JSONB,
  request_params JSONB,
  query_params JSONB,
  search_keyword TEXT,
  matched_rule_id INTEGER,
  matched_rule_name VARCHAR(255),
  label_id INTEGER,
  label_name VARCHAR(255),
  host VARCHAR(255),
  path TEXT,
  content_type VARCHAR(255),
  is_json INTEGER,
  response_size INTEGER,
  request_body_raw TEXT,
  response_status INTEGER,
  response_body JSONB,
  response_body_text TEXT,
  response_body_raw TEXT,
  duration_ms INTEGER,
  page_url TEXT,
  page_title VARCHAR(500),
  captured_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS capture_rules (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  creator_phone VARCHAR(32),
  name VARCHAR(255) NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  label_id INTEGER,
  label_name VARCHAR(255),
  method VARCHAR(12),
  url_pattern TEXT NOT NULL,
  url_match_type VARCHAR(20) NOT NULL DEFAULT 'contains',
  params_filter JSONB,
  response_list_path VARCHAR(500),
  field_mapping JSONB,
  remark TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_rule_selections (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rule_id INTEGER NOT NULL REFERENCES capture_rules(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, rule_id)
);

CREATE TABLE IF NOT EXISTS data_labels (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  creator_phone VARCHAR(32),
  name VARCHAR(255) NOT NULL,
  table_name VARCHAR(255) NOT NULL,
  remark TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS label_data_records (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id INTEGER REFERENCES capture_sessions(id) ON DELETE CASCADE,
  api_id INTEGER REFERENCES captured_apis(id) ON DELETE CASCADE,
  label_id INTEGER,
  label_name VARCHAR(255),
  rule_id INTEGER,
  rule_name VARCHAR(255),
  row_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  raw_item JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS channel_product_records (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id INTEGER REFERENCES capture_sessions(id) ON DELETE CASCADE,
  api_id INTEGER REFERENCES captured_apis(id) ON DELETE CASCADE,
  label_id INTEGER,
  label_name VARCHAR(255),
  platform_user VARCHAR(255),
  source_user_id VARCHAR(255),
  platform VARCHAR(255),
  source_created_at VARCHAR(255),
  search_keyword TEXT,
  channel_title TEXT,
  channel_url TEXT,
  sku_id VARCHAR(255),
  price VARCHAR(255),
  sales VARCHAR(255),
  channel_image TEXT,
  shop_name TEXT,
  shop_id VARCHAR(255),
  shop_url TEXT,
  ad_tag TEXT,
  product_activity TEXT,
  discount_strength TEXT,
  platform_category TEXT,
  product_info TEXT,
  ranking_info TEXT,
  ship_from TEXT,
  product_marketing TEXT,
  shop_marketing TEXT,
  article_number VARCHAR(255),
  serial_number VARCHAR(255),
  core_tags TEXT,
  activity_source TEXT,
  channel_page_title TEXT,
  shop_tags TEXT,
  raw_item JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_capture_records_user_id ON capture_records(user_id);
CREATE INDEX IF NOT EXISTS idx_capture_records_capture_time ON capture_records(capture_time);
CREATE INDEX IF NOT EXISTS idx_capture_records_url ON capture_records USING gin (url gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_capture_records_xhr_data ON capture_records USING gin (xhr_data);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_user_id ON capture_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_started_at ON capture_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_ended_at ON capture_sessions(ended_at);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_captured_at ON capture_sessions(captured_at);
CREATE INDEX IF NOT EXISTS idx_captured_apis_user_id ON captured_apis(user_id);
CREATE INDEX IF NOT EXISTS idx_captured_apis_session_id ON captured_apis(session_id);
CREATE INDEX IF NOT EXISTS idx_captured_apis_captured_at ON captured_apis(captured_at);
CREATE INDEX IF NOT EXISTS idx_captured_apis_method ON captured_apis(method);
CREATE INDEX IF NOT EXISTS idx_captured_apis_response_status ON captured_apis(response_status);
CREATE INDEX IF NOT EXISTS idx_captured_apis_host ON captured_apis(host);
CREATE INDEX IF NOT EXISTS idx_captured_apis_search_keyword ON captured_apis USING gin (search_keyword gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_captured_apis_matched_rule_id ON captured_apis(matched_rule_id);
CREATE INDEX IF NOT EXISTS idx_captured_apis_label_id ON captured_apis(label_id);
CREATE INDEX IF NOT EXISTS idx_captured_apis_label_name ON captured_apis(label_name);
CREATE INDEX IF NOT EXISTS idx_captured_apis_url ON captured_apis USING gin (url gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_captured_apis_request_params ON captured_apis USING gin (request_params);
CREATE INDEX IF NOT EXISTS idx_captured_apis_response_body ON captured_apis USING gin (response_body);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_user_id ON channel_product_records(user_id);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_session_id ON channel_product_records(session_id);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_api_id ON channel_product_records(api_id);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_label_id ON channel_product_records(label_id);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_label_name ON channel_product_records(label_name);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_sku_id ON channel_product_records(sku_id);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_shop_id ON channel_product_records(shop_id);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_platform ON channel_product_records(platform);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_created_at ON channel_product_records(created_at);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_title ON channel_product_records USING gin (channel_title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_url ON channel_product_records USING gin (channel_url gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_channel_product_records_raw_item ON channel_product_records USING gin (raw_item);
CREATE INDEX IF NOT EXISTS idx_capture_rules_user_id ON capture_rules(user_id);
CREATE INDEX IF NOT EXISTS idx_capture_rules_enabled ON capture_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_capture_rules_label_id ON capture_rules(label_id);
CREATE INDEX IF NOT EXISTS idx_user_rule_selections_user_id ON user_rule_selections(user_id);
CREATE INDEX IF NOT EXISTS idx_user_rule_selections_rule_id ON user_rule_selections(rule_id);
CREATE INDEX IF NOT EXISTS idx_data_labels_user_id ON data_labels(user_id);
CREATE INDEX IF NOT EXISTS idx_data_labels_name ON data_labels(name);
CREATE INDEX IF NOT EXISTS idx_data_labels_table_name ON data_labels(table_name);
CREATE INDEX IF NOT EXISTS idx_label_data_records_user_id ON label_data_records(user_id);
CREATE INDEX IF NOT EXISTS idx_label_data_records_label_id ON label_data_records(label_id);
CREATE INDEX IF NOT EXISTS idx_label_data_records_rule_id ON label_data_records(rule_id);
CREATE INDEX IF NOT EXISTS idx_label_data_records_row_data ON label_data_records USING gin (row_data);
