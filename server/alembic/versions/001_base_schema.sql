-- Revision ID: 001_base_schema
-- Revises:
-- Create Date: 2026-09-07

BEGIN;

CREATE TABLE IF NOT EXISTS devices (
                        id TEXT PRIMARY KEY,
                        alias TEXT,
                        owner_id TEXT,
                        device_fingerprint TEXT,
                        platform TEXT DEFAULT 'android',
                        app_version TEXT,
                        os_version TEXT,
                        model TEXT,
                        imei_hash TEXT,
                        sim_serial_hash TEXT,
                        device_key_hash TEXT,
                        last_seen TIMESTAMPTZ,
                        registered TIMESTAMPTZ DEFAULT NOW(),
                        is_stolen BOOLEAN DEFAULT FALSE,
                        theft_confirmed_at TIMESTAMPTZ,
                        operating_mode TEXT DEFAULT 'normal',
                        sentinel_score INTEGER DEFAULT 0,
                        capture_armed BOOLEAN,
                        location_mode TEXT,
                        archived_at TIMESTAMP,
                        -- Per-device alert recipients/preferences (NULL = global defaults)
                        alert_phone TEXT,
                        alert_email TEXT,
                        alert_channels TEXT,
                        enabled_types TEXT,
                        quiet_hours_start INTEGER,
                        quiet_hours_end INTEGER,
                        -- Offline Command Relay (SMS)
                        sms_phone TEXT,
                        sms_commands_enabled BOOLEAN DEFAULT FALSE
                    );

CREATE TABLE IF NOT EXISTS locations (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        lat DOUBLE PRECISION NOT NULL,
                        lng DOUBLE PRECISION NOT NULL,
                        altitude DOUBLE PRECISION,
                        accuracy_horizontal DOUBLE PRECISION,
                        accuracy_vertical DOUBLE PRECISION,
                        confidence_level TEXT DEFAULT 'UNKNOWN',
                        speed DOUBLE PRECISION,
                        bearing DOUBLE PRECISION,
                        activity_type TEXT,
                        step_count INTEGER,
                        provider TEXT,
                        gps_satellite_count INTEGER,
                        wifi_bssids TEXT,
                        cell_tower_ids TEXT,
                        ble_devices_nearby INTEGER,
                        battery_percent INTEGER,
                        is_charging BOOLEAN,
                        network_type TEXT,
                        signal_strength_dbm INTEGER,
                        is_location_enabled BOOLEAN,
                        is_airplane_mode BOOLEAN,
                        sim_changed BOOLEAN DEFAULT FALSE,
                        sim_serial_hash TEXT,
                        sentinel_score INTEGER DEFAULT 0,
                        threat_level TEXT DEFAULT 'SAFE',
                        anomalies TEXT,
                        device_timestamp TIMESTAMPTZ,
                        server_timestamp TIMESTAMPTZ DEFAULT NOW(),
                        was_queued BOOLEAN DEFAULT FALSE,
                        queued_at TIMESTAMPTZ,
                        queue_position INTEGER,
                        ping_sequence INTEGER,
                        location_encrypted BOOLEAN DEFAULT FALSE,
                        -- At-rest encryption (v1.5): base64 AES-256-GCM ciphertext
                        -- for encrypted rows (lat/lng hold 0.0 placeholders);
                        -- readers decrypt via encryption.decrypt_location_row().
                        location_data TEXT
                    );

CREATE TABLE IF NOT EXISTS media (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        type TEXT NOT NULL,
                        data_b64 TEXT NOT NULL,
                        lat DOUBLE PRECISION,
                        lng DOUBLE PRECISION,
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        evidence_case_id TEXT,
                        sha256_hash TEXT,
                        file_path TEXT,
                        file_size BIGINT
                    );

CREATE TABLE IF NOT EXISTS commands (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        command TEXT NOT NULL,
                        params TEXT,
                        status TEXT DEFAULT 'pending',
                        priority INTEGER DEFAULT 5,
                        issued_at TIMESTAMPTZ DEFAULT NOW(),
                        executed_at TIMESTAMPTZ,
                        expires_at TIMESTAMPTZ,
                        failure_reason TEXT,
                        delivery_channel TEXT
                    );

CREATE TABLE IF NOT EXISTS evidence_cases (
                        id TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        theft_time TIMESTAMPTZ,
                        status TEXT DEFAULT 'active',
                        location_count INTEGER DEFAULT 0,
                        photo_count INTEGER DEFAULT 0,
                        audio_count INTEGER DEFAULT 0,
                        sha256_chain TEXT,
                        pdf_generated BOOLEAN DEFAULT FALSE
                    );

CREATE TABLE IF NOT EXISTS alerts (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        alert_type TEXT NOT NULL,
                        channel TEXT NOT NULL,
                        recipient TEXT,
                        message TEXT,
                        sent_at TIMESTAMPTZ DEFAULT NOW(),
                        delivered BOOLEAN DEFAULT FALSE
                    );

CREATE TABLE IF NOT EXISTS heartbeats (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        battery_percent INTEGER,
                        is_charging BOOLEAN,
                        network_type TEXT,
                        device_admin_active BOOLEAN,
                        sim_hash TEXT,
                        app_version TEXT,
                        pending_evidence_count INTEGER DEFAULT 0
                    );

CREATE TABLE IF NOT EXISTS geofences (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        name TEXT,
                        center_lat DOUBLE PRECISION NOT NULL,
                        center_lng DOUBLE PRECISION NOT NULL,
                        radius_meters DOUBLE PRECISION NOT NULL,
                        is_safe_zone BOOLEAN DEFAULT TRUE,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        -- v1.5 auto-actions + persisted transition state
                        -- (parity with the SQLite schema — enforced by
                        -- tests/test_postgres_adapter_parity.py).
                        auto_action TEXT,
                        last_inside BOOLEAN
                    );

CREATE TABLE IF NOT EXISTS guardian_profiles (
                        user_id TEXT PRIMARY KEY,
                        opted_in BOOLEAN DEFAULT TRUE,
                        radius_km INTEGER DEFAULT 20,
                        handle TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ
                    );

CREATE TABLE IF NOT EXISTS recovery_requests (
                        id TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        owner_id TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        description TEXT,
                        last_lat DOUBLE PRECISION,
                        last_lng DOUBLE PRECISION,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        closed_at TIMESTAMPTZ,
                        closed_reason TEXT,
                        beacon_token TEXT
                    );

CREATE TABLE IF NOT EXISTS recovery_sightings (
                        id BIGSERIAL PRIMARY KEY,
                        request_id TEXT NOT NULL REFERENCES recovery_requests(id),
                        guardian_id TEXT NOT NULL,
                        guardian_handle TEXT,
                        lat DOUBLE PRECISION NOT NULL,
                        lng DOUBLE PRECISION NOT NULL,
                        note TEXT,
                        hop_count INTEGER DEFAULT 0,
                        relayed BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

CREATE TABLE IF NOT EXISTS p2p_pairings (
                        id TEXT PRIMARY KEY,
                        owner_user_id TEXT NOT NULL,
                        device_a TEXT NOT NULL,
                        device_b TEXT,
                        pair_secret_enc TEXT,
                        pair_code_hash TEXT,
                        pair_code_expires TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        completed_at TIMESTAMPTZ
                    );

CREATE TABLE IF NOT EXISTS audit_log (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        action TEXT NOT NULL,
                        actor TEXT,
                        ip_address TEXT,
                        details TEXT
                    );

CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        display_name TEXT,
                        tier TEXT DEFAULT 'free',
                        is_active BOOLEAN DEFAULT TRUE,
                        email_verified BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        last_login TIMESTAMPTZ,
                        totp_secret_enc TEXT,
                        totp_enabled INTEGER DEFAULT 0,
                        totp_last_period INTEGER DEFAULT 0
                    );

CREATE TABLE IF NOT EXISTS fcm_tokens (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        fcm_token TEXT NOT NULL,
                        platform TEXT DEFAULT 'android',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(device_id, fcm_token)
                    );

CREATE TABLE IF NOT EXISTS error_log (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        level TEXT NOT NULL DEFAULT 'ERROR',
                        source TEXT,
                        message TEXT NOT NULL,
                        traceback TEXT,
                        request_method TEXT,
                        request_path TEXT,
                        request_ip TEXT,
                        user_agent TEXT,
                        device_id TEXT,
                        resolved BOOLEAN DEFAULT FALSE,
                        resolved_at TIMESTAMPTZ,
                        resolved_by TEXT,
                        notes TEXT
                    );

CREATE TABLE IF NOT EXISTS password_reset_tokens (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        token_hash TEXT NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        used INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

CREATE TABLE IF NOT EXISTS email_verify_tokens (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        token_hash TEXT NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        used INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

CREATE TABLE IF NOT EXISTS cell_location_cache (
                        fingerprint TEXT PRIMARY KEY,
                        lat DOUBLE PRECISION NOT NULL,
                        lng DOUBLE PRECISION NOT NULL,
                        accuracy_meters DOUBLE PRECISION,
                        provider TEXT,
                        resolved_at TIMESTAMPTZ DEFAULT NOW()
                    );

CREATE TABLE IF NOT EXISTS rate_limits (
                        id BIGSERIAL PRIMARY KEY,
                        identifier TEXT NOT NULL,
                        action TEXT NOT NULL,
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );

CREATE TABLE IF NOT EXISTS revoked_tokens (
                        jti TEXT PRIMARY KEY,
                        revoked_at TIMESTAMPTZ DEFAULT NOW(),
                        reason TEXT
                    );

CREATE TABLE IF NOT EXISTS analytics_events (
                        id BIGSERIAL PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        device_id TEXT,
                        user_id TEXT,
                        metadata TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

CREATE TABLE IF NOT EXISTS circles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    invite_code TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (owner_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS circle_members (
                        id TEXT PRIMARY KEY,
                        circle_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'member',
                        joined_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (circle_id, user_id),
                        FOREIGN KEY (circle_id) REFERENCES circles(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    );

CREATE TABLE IF NOT EXISTS circle_devices (
                        id TEXT PRIMARY KEY,
                        circle_id TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        shared_by TEXT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (circle_id, device_id),
                        FOREIGN KEY (circle_id) REFERENCES circles(id) ON DELETE CASCADE,
                        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                        FOREIGN KEY (shared_by) REFERENCES users(id)
                    );

CREATE TABLE IF NOT EXISTS device_shares (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL REFERENCES devices(id),
                    grantee_user_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    created_by TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (device_id, grantee_user_id)
                );

                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    key_prefix TEXT NOT NULL UNIQUE,
                    key_hash TEXT NOT NULL,
                    scopes TEXT NOT NULL DEFAULT 'devices:read',
                    key_type TEXT NOT NULL DEFAULT 'live',
                    request_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    last_used_at TIMESTAMPTZ,
                    expires_at TIMESTAMPTZ,
                    revoked_at TIMESTAMPTZ
                );

                CREATE INDEX IF NOT EXISTS idx_devices_key_hash ON devices(device_key_hash);

CREATE INDEX IF NOT EXISTS idx_device_shares_device ON device_shares(device_id);

CREATE INDEX IF NOT EXISTS idx_device_shares_grantee ON device_shares(grantee_user_id);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);

CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);

CREATE INDEX IF NOT EXISTS idx_recovery_requests_status ON recovery_requests(status);

CREATE INDEX IF NOT EXISTS idx_recovery_requests_owner ON recovery_requests(owner_id);

CREATE INDEX IF NOT EXISTS idx_recovery_sightings_request ON recovery_sightings(request_id);

CREATE INDEX IF NOT EXISTS idx_p2p_pairings_owner ON p2p_pairings(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_p2p_pairings_code ON p2p_pairings(pair_code_hash);

CREATE INDEX IF NOT EXISTS idx_analytics_type_time ON analytics_events(event_type, created_at);

CREATE INDEX IF NOT EXISTS idx_analytics_device ON analytics_events(device_id, created_at);

CREATE TABLE IF NOT EXISTS payments (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    reference TEXT UNIQUE NOT NULL,
                    amount DOUBLE PRECISION NOT NULL,
                    plan TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    paid_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);

CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(reference);

CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

CREATE INDEX IF NOT EXISTS idx_locations_device ON locations(device_id);

CREATE INDEX IF NOT EXISTS idx_locations_timestamp ON locations(server_timestamp);

CREATE INDEX IF NOT EXISTS idx_locations_dedup ON
                        locations(device_id, ping_sequence, device_timestamp);

CREATE INDEX IF NOT EXISTS idx_media_device ON media(device_id);

CREATE INDEX IF NOT EXISTS idx_commands_device ON commands(device_id);

CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);

CREATE INDEX IF NOT EXISTS idx_heartbeats_device ON heartbeats(device_id);

CREATE INDEX IF NOT EXISTS idx_geofences_device ON geofences(device_id);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);

CREATE INDEX IF NOT EXISTS idx_rate_limits_identifier ON rate_limits(identifier, action);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE INDEX IF NOT EXISTS idx_fcm_tokens_device ON fcm_tokens(device_id);

CREATE INDEX IF NOT EXISTS idx_error_log_timestamp ON error_log(timestamp);

CREATE INDEX IF NOT EXISTS idx_error_log_resolved ON error_log(resolved);

CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens(user_id);

CREATE INDEX IF NOT EXISTS idx_email_verify_user ON email_verify_tokens(user_id);

CREATE TABLE IF NOT EXISTS mesh_beacons (
                    device_id TEXT PRIMARY KEY,
                    beacon_token TEXT NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    registered_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS mesh_sightings (
                    id BIGSERIAL PRIMARY KEY,
                    beacon_device_id TEXT NOT NULL,
                    finder_device_id TEXT NOT NULL,
                    lat DOUBLE PRECISION NOT NULL,
                    lng DOUBLE PRECISION NOT NULL,
                    accuracy DOUBLE PRECISION,
                    rssi INTEGER,
                    reported_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_mesh_sightings_beacon
                        ON mesh_sightings(beacon_device_id, reported_at);

CREATE INDEX IF NOT EXISTS idx_mesh_sightings_finder
                        ON mesh_sightings(finder_device_id, reported_at);

CREATE INDEX IF NOT EXISTS idx_circles_owner ON circles(owner_id);

CREATE INDEX IF NOT EXISTS idx_circles_invite ON circles(invite_code);

CREATE INDEX IF NOT EXISTS idx_circle_members_circle ON circle_members(circle_id);

CREATE INDEX IF NOT EXISTS idx_circle_members_user ON circle_members(user_id);

CREATE INDEX IF NOT EXISTS idx_circle_devices_circle ON circle_devices(circle_id);

CREATE INDEX IF NOT EXISTS idx_circle_devices_device ON circle_devices(device_id);

CREATE TABLE IF NOT EXISTS tracking_consents (
                    id BIGSERIAL PRIMARY KEY,
                    device_id TEXT NOT NULL REFERENCES devices(id),
                    grantee_user_id TEXT NOT NULL,
                    grantor_user_id TEXT NOT NULL,
                    consent_given BOOLEAN NOT NULL DEFAULT TRUE,
                    consent_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    consent_method TEXT NOT NULL DEFAULT 'explicit_grant',
                    revoked BOOLEAN DEFAULT FALSE,
                    revocation_timestamp TIMESTAMPTZ,
                    revocation_method TEXT
                );

                CREATE TABLE IF NOT EXISTS abuse_reports (
                    id TEXT PRIMARY KEY,
                    reporter_user_id TEXT NOT NULL,
                    reported_user_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    evidence TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    resolved_at TIMESTAMPTZ,
                    resolved_by TEXT,
                    resolution_notes TEXT
                );

                CREATE TABLE IF NOT EXISTS privacy_consents (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    consent_type TEXT NOT NULL,
                    consent_given BOOLEAN NOT NULL,
                    consent_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    ip_address TEXT,
                    user_agent TEXT,
                    revoked BOOLEAN DEFAULT FALSE,
                    revocation_timestamp TIMESTAMPTZ
                );

                CREATE TABLE IF NOT EXISTS data_export_requests (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    requested_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    download_url TEXT,
                    expires_at TIMESTAMPTZ
                );

                CREATE INDEX IF NOT EXISTS idx_tracking_consents_device ON tracking_consents(device_id);

CREATE INDEX IF NOT EXISTS idx_tracking_consents_grantee ON tracking_consents(grantee_user_id);

CREATE INDEX IF NOT EXISTS idx_abuse_reports_status ON abuse_reports(status);

CREATE INDEX IF NOT EXISTS idx_abuse_reports_reported ON abuse_reports(reported_user_id);

CREATE INDEX IF NOT EXISTS idx_privacy_consents_user ON privacy_consents(user_id);

COMMIT;
