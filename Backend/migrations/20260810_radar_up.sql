CREATE TABLE IF NOT EXISTS radar_targets (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    steam_id VARCHAR(32) NOT NULL,
    alias VARCHAR(100) NULL,
    tags JSON NOT NULL,
    note VARCHAR(500) NULL,
    manual_cs_level INT NULL,
    service_medal VARCHAR(16) NOT NULL DEFAULT 'unknown',
    added_by VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_radar_targets_steam_id (steam_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS radar_sessions (
    id CHAR(36) NOT NULL,
    mode VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    started_by VARCHAR(128) NOT NULL,
    started_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    last_tick_at DATETIME NULL,
    error_summary VARCHAR(500) NULL,
    PRIMARY KEY (id),
    KEY ix_radar_sessions_status_expires (status, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS radar_observations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    target_id BIGINT UNSIGNED NOT NULL,
    session_id CHAR(36) NULL,
    status VARCHAR(24) NOT NULL,
    personaname VARCHAR(255) NULL,
    avatar_url VARCHAR(500) NULL,
    profile_url VARCHAR(500) NULL,
    privacy_state INT NULL,
    persona_state INT NULL,
    game_id VARCHAR(32) NULL,
    game_extra_info VARCHAR(255) NULL,
    game_server_ip VARCHAR(128) NULL,
    lobby_steam_id VARCHAR(32) NULL,
    group_key VARCHAR(160) NULL,
    account_created_at DATETIME NULL,
    cs2_playtime_minutes INT NULL,
    vac_banned BOOLEAN NULL,
    game_ban_count INT NULL,
    risk_signals JSON NOT NULL,
    observed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_radar_observations_target_time (target_id, observed_at),
    KEY ix_radar_observations_session (session_id),
    CONSTRAINT fk_radar_observation_target FOREIGN KEY (target_id) REFERENCES radar_targets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS web_login_challenges (
    token_hash CHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    user_uuid VARCHAR(128) NULL,
    expires_at DATETIME NOT NULL,
    consumed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (token_hash),
    KEY ix_web_login_challenges_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
