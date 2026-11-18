-- Wenchu formal knowledge schema, v1.
-- This file is applied only to a new/managed knowledge_prototype.sqlite3 database.
-- No demo or legacy records are seeded here; all knowledge starts unapproved.

CREATE TABLE RecipeCategory (
    category_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_category_id TEXT REFERENCES RecipeCategory(category_id) ON DELETE RESTRICT,
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE Recipe (
    recipe_id TEXT PRIMARY KEY,
    standard_name TEXT NOT NULL,
    category_id TEXT REFERENCES RecipeCategory(category_id) ON DELETE RESTRICT,
    description TEXT NOT NULL DEFAULT '',
    record_status TEXT NOT NULL DEFAULT 'active' CHECK (record_status IN ('active','archived')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE UNIQUE INDEX idx_recipe_active_standard_name
    ON Recipe(standard_name COLLATE NOCASE) WHERE record_status = 'active';

CREATE TABLE RecipeVersion (
    recipe_version_id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL REFERENCES Recipe(recipe_id) ON DELETE RESTRICT,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    servings REAL CHECK (servings IS NULL OR servings > 0),
    serving_unit TEXT,
    difficulty TEXT,
    prep_time_minutes INTEGER CHECK (prep_time_minutes IS NULL OR prep_time_minutes >= 0),
    cook_time_minutes INTEGER CHECK (cook_time_minutes IS NULL OR cook_time_minutes >= 0),
    change_note TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (recipe_id, version_no)
);
CREATE INDEX idx_recipe_version_review
    ON RecipeVersion(review_status, next_review_at);
CREATE INDEX idx_recipe_version_recipe
    ON RecipeVersion(recipe_id, version_no DESC);

CREATE TABLE RecipeAlias (
    alias_id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL REFERENCES Recipe(recipe_id) ON DELETE RESTRICT,
    alias_text TEXT NOT NULL,
    normalized_alias_text TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'zh-Hans',
    alias_type TEXT NOT NULL DEFAULT 'common_name',
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
-- SQLite cannot use a moving time predicate in a unique index; approved aliases are
-- unique conservatively, and retrieval additionally excludes aliases past next_review_at.
CREATE UNIQUE INDEX idx_recipe_alias_approved_normalized
    ON RecipeAlias(normalized_alias_text) WHERE review_status = 'approved';
CREATE INDEX idx_recipe_alias_recipe ON RecipeAlias(recipe_id, review_status);

CREATE TABLE IngredientCategory (
    category_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE Ingredient (
    ingredient_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    category_id TEXT REFERENCES IngredientCategory(category_id) ON DELETE RESTRICT,
    default_unit TEXT,
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_ingredient_review ON Ingredient(review_status, next_review_at);

-- Ingredient rows inside a recipe version are reviewed as part of that whole package.
CREATE TABLE RecipeIngredient (
    recipe_ingredient_id TEXT PRIMARY KEY,
    recipe_version_id TEXT NOT NULL REFERENCES RecipeVersion(recipe_version_id) ON DELETE CASCADE,
    ingredient_id TEXT NOT NULL REFERENCES Ingredient(ingredient_id) ON DELETE RESTRICT,
    amount REAL CHECK (amount IS NULL OR amount >= 0),
    unit TEXT,
    role TEXT NOT NULL DEFAULT 'ingredient',
    is_optional INTEGER NOT NULL DEFAULT 0 CHECK (is_optional IN (0,1)),
    prep_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (recipe_version_id, ingredient_id, role)
);
CREATE INDEX idx_recipe_ingredient_version ON RecipeIngredient(recipe_version_id);

CREATE TABLE IngredientSubstitution (
    substitution_id TEXT PRIMARY KEY,
    from_ingredient_id TEXT NOT NULL REFERENCES Ingredient(ingredient_id) ON DELETE RESTRICT,
    to_ingredient_id TEXT NOT NULL REFERENCES Ingredient(ingredient_id) ON DELETE RESTRICT,
    recipe_version_id TEXT REFERENCES RecipeVersion(recipe_version_id) ON DELETE CASCADE,
    ratio_or_amount TEXT NOT NULL DEFAULT '',
    effect_note TEXT NOT NULL DEFAULT '',
    limitations TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (from_ingredient_id <> to_ingredient_id)
);
CREATE INDEX idx_ingredient_substitution_from ON IngredientSubstitution(from_ingredient_id, review_status);
CREATE INDEX idx_ingredient_substitution_version ON IngredientSubstitution(recipe_version_id);

CREATE TABLE Cookware (
    cookware_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    cookware_type TEXT NOT NULL DEFAULT 'tool',
    material TEXT,
    heat_source_compatibility TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_cookware_review ON Cookware(review_status, next_review_at);

CREATE TABLE CookingMethod (
    method_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_cooking_method_review ON CookingMethod(review_status, next_review_at);

CREATE TABLE RecipeCookware (
    recipe_cookware_id TEXT PRIMARY KEY,
    recipe_version_id TEXT NOT NULL REFERENCES RecipeVersion(recipe_version_id) ON DELETE CASCADE,
    cookware_id TEXT NOT NULL REFERENCES Cookware(cookware_id) ON DELETE RESTRICT,
    use_role TEXT NOT NULL DEFAULT 'optional' CHECK (use_role IN ('required','recommended','available','optional')),
    use_stage TEXT NOT NULL DEFAULT '',
    conditions TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (recipe_version_id, cookware_id, use_role)
);
CREATE INDEX idx_recipe_cookware_version ON RecipeCookware(recipe_version_id);

CREATE TABLE CookwareSubstitution (
    cookware_substitution_id TEXT PRIMARY KEY,
    recipe_version_id TEXT NOT NULL REFERENCES RecipeVersion(recipe_version_id) ON DELETE CASCADE,
    required_cookware_id TEXT NOT NULL REFERENCES Cookware(cookware_id) ON DELETE RESTRICT,
    alternative_cookware_id TEXT NOT NULL REFERENCES Cookware(cookware_id) ON DELETE RESTRICT,
    conditions TEXT NOT NULL DEFAULT '',
    tradeoff_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (required_cookware_id <> alternative_cookware_id),
    UNIQUE (recipe_version_id, required_cookware_id, alternative_cookware_id)
);
CREATE INDEX idx_cookware_substitution_version ON CookwareSubstitution(recipe_version_id);

CREATE TABLE RecipeMethod (
    recipe_method_id TEXT PRIMARY KEY,
    recipe_version_id TEXT NOT NULL REFERENCES RecipeVersion(recipe_version_id) ON DELETE CASCADE,
    method_id TEXT NOT NULL REFERENCES CookingMethod(method_id) ON DELETE RESTRICT,
    role TEXT NOT NULL DEFAULT 'main' CHECK (role IN ('main','supporting')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (recipe_version_id, method_id)
);
CREATE INDEX idx_recipe_method_version ON RecipeMethod(recipe_version_id);

CREATE TABLE RecipeStep (
    step_id TEXT PRIMARY KEY,
    recipe_version_id TEXT NOT NULL REFERENCES RecipeVersion(recipe_version_id) ON DELETE CASCADE,
    step_no INTEGER NOT NULL CHECK (step_no > 0),
    instruction TEXT NOT NULL,
    method_id TEXT REFERENCES CookingMethod(method_id) ON DELETE RESTRICT,
    heat_level TEXT,
    temperature_c REAL,
    duration_seconds INTEGER CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    safety_reminder TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (recipe_version_id, step_no)
);
CREATE INDEX idx_recipe_step_version ON RecipeStep(recipe_version_id, step_no);

CREATE TABLE StepIngredient (
    step_id TEXT NOT NULL REFERENCES RecipeStep(step_id) ON DELETE CASCADE,
    ingredient_id TEXT NOT NULL REFERENCES Ingredient(ingredient_id) ON DELETE RESTRICT,
    amount REAL CHECK (amount IS NULL OR amount >= 0),
    unit TEXT,
    PRIMARY KEY (step_id, ingredient_id)
);
CREATE TABLE StepCookware (
    step_id TEXT NOT NULL REFERENCES RecipeStep(step_id) ON DELETE CASCADE,
    cookware_id TEXT NOT NULL REFERENCES Cookware(cookware_id) ON DELETE RESTRICT,
    PRIMARY KEY (step_id, cookware_id)
);

CREATE TABLE Experience (
    experience_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    claim TEXT NOT NULL,
    conditions TEXT NOT NULL DEFAULT '',
    exceptions TEXT NOT NULL DEFAULT '',
    confidence_level TEXT CHECK (confidence_level IS NULL OR confidence_level IN ('low','medium','high')),
    safety_impact TEXT NOT NULL DEFAULT 'ordinary'
        CHECK (safety_impact IN ('ordinary','important','safety_critical')),
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_experience_review ON Experience(review_status, next_review_at);

CREATE TABLE ExperienceRecipe (
    experience_recipe_id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL REFERENCES Experience(experience_id) ON DELETE CASCADE,
    recipe_id TEXT REFERENCES Recipe(recipe_id) ON DELETE RESTRICT,
    recipe_version_id TEXT REFERENCES RecipeVersion(recipe_version_id) ON DELETE RESTRICT,
    applicability_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (recipe_id IS NOT NULL OR recipe_version_id IS NOT NULL)
);
CREATE INDEX idx_experience_recipe_exp ON ExperienceRecipe(experience_id);
CREATE TABLE ExperienceCookware (
    experience_cookware_id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL REFERENCES Experience(experience_id) ON DELETE CASCADE,
    cookware_id TEXT NOT NULL REFERENCES Cookware(cookware_id) ON DELETE RESTRICT,
    applicability_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (experience_id, cookware_id)
);
CREATE INDEX idx_experience_cookware_exp ON ExperienceCookware(experience_id);
CREATE TABLE ExperienceMethod (
    experience_method_id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL REFERENCES Experience(experience_id) ON DELETE CASCADE,
    method_id TEXT NOT NULL REFERENCES CookingMethod(method_id) ON DELETE RESTRICT,
    applicability_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (experience_id, method_id)
);
CREATE INDEX idx_experience_method_exp ON ExperienceMethod(experience_id);

CREATE TABLE KnowledgeSource (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    publisher TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    url TEXT,
    published_at TEXT,
    collected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    usage_policy TEXT NOT NULL DEFAULT 'summary_only'
        CHECK (usage_policy IN ('summary_only','link_only','licensed_excerpt','internal_only')),
    rights_basis TEXT NOT NULL DEFAULT '',
    rights_note TEXT NOT NULL DEFAULT '',
    source_status TEXT NOT NULL DEFAULT 'pending_check'
        CHECK (source_status IN ('accessible','inaccessible','pending_check','not_applicable')),
    link_checked_at TEXT,
    next_link_check_at TEXT,
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    rights_review_status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (rights_review_status IN ('pending_review','approved','needs_update','revoked','rejected')),
    rights_reviewed_by TEXT,
    rights_reviewed_at TEXT,
    next_rights_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK ((url IS NULL AND source_status = 'not_applicable') OR url IS NOT NULL)
);
CREATE INDEX idx_knowledge_source_review ON KnowledgeSource(review_status, rights_review_status);
CREATE INDEX idx_knowledge_source_link_check ON KnowledgeSource(source_status, next_link_check_at);

CREATE TABLE EvidenceLink (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES KnowledgeSource(source_id) ON DELETE RESTRICT,
    -- target_type + target_id is intentionally polymorphic; SQLite cannot enforce its FK.
    -- Use target_type values from the application allowlist and validate target existence there.
    target_type TEXT NOT NULL CHECK (target_type IN ('recipe_version','experience','recipe_step','ingredient_substitution','cookware_substitution')),
    target_id TEXT NOT NULL,
    locator TEXT NOT NULL DEFAULT '',
    our_summary TEXT NOT NULL DEFAULT '',
    evidence_note TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source_id, target_type, target_id, locator)
);
CREATE INDEX idx_evidence_target ON EvidenceLink(target_type, target_id, review_status);
CREATE INDEX idx_evidence_source ON EvidenceLink(source_id, review_status);

CREATE TABLE ReviewRecord (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    review_type TEXT NOT NULL CHECK (review_type IN ('recipe_version_package','experience','source_content','source_link','source_rights','alias','shared_entity')),
    decision TEXT NOT NULL CHECK (decision IN ('approved','pending_review','returned','rejected','revoked','reopened','checked_accessible','checked_inaccessible','rights_approved','rights_revoked','needs_update','superseded')),
    reviewer_id TEXT,
    reviewed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    reason TEXT NOT NULL DEFAULT '',
    previous_status TEXT,
    new_status TEXT
);
CREATE INDEX idx_review_record_target ON ReviewRecord(target_type, target_id, reviewed_at DESC);
CREATE INDEX idx_review_record_date ON ReviewRecord(reviewed_at DESC);

-- Cross-visitor AI history is separate from curated recipes/experiences.
-- No raw image or raw prompt/notes columns exist. Consent=false rows cannot contain
-- analysis JSON or reusable request/profile fingerprints.
CREATE TABLE AnalysisRecord (
    analysis_id TEXT PRIMARY KEY,
    normalized_recipe_name TEXT NOT NULL DEFAULT '',
    analysis_json TEXT,
    request_fingerprint TEXT,
    kitchen_profile_fingerprint TEXT,
    consent_to_share INTEGER NOT NULL DEFAULT 0 CHECK (consent_to_share IN (0,1)),
    review_status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (review_status IN ('draft','pending_review','approved','needs_update','rejected','superseded')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    next_review_at TEXT,
    CHECK (consent_to_share = 1 OR
           (analysis_json IS NULL AND request_fingerprint IS NULL AND kitchen_profile_fingerprint IS NULL))
);
CREATE INDEX idx_analysis_review ON AnalysisRecord(review_status, next_review_at);
