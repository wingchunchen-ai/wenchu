-- Database-level safeguards: substantive package/experience edits reopen review.
-- These triggers do not auto-approve anything; they fail closed to needs_update.

CREATE TRIGGER trg_recipeingredient_reopen_insert AFTER INSERT ON RecipeIngredient
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeIngredient', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipeingredient_reopen_update AFTER UPDATE ON RecipeIngredient
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeIngredient', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipeingredient_reopen_delete AFTER DELETE ON RecipeIngredient
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeIngredient', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipecookware_reopen_insert AFTER INSERT ON RecipeCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipecookware_reopen_update AFTER UPDATE ON RecipeCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipecookware_reopen_delete AFTER DELETE ON RecipeCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_cookwaresubstitution_reopen_insert AFTER INSERT ON CookwareSubstitution
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: CookwareSubstitution', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_cookwaresubstitution_reopen_update AFTER UPDATE ON CookwareSubstitution
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: CookwareSubstitution', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_cookwaresubstitution_reopen_delete AFTER DELETE ON CookwareSubstitution
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: CookwareSubstitution', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipemethod_reopen_insert AFTER INSERT ON RecipeMethod
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeMethod', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipemethod_reopen_update AFTER UPDATE ON RecipeMethod
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeMethod', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipemethod_reopen_delete AFTER DELETE ON RecipeMethod
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeMethod', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipestep_reopen_insert AFTER INSERT ON RecipeStep
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeStep', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipestep_reopen_update AFTER UPDATE ON RecipeStep
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeStep', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipestep_reopen_delete AFTER DELETE ON RecipeStep
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: RecipeStep', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_ingredient_substitution_reopen_insert AFTER INSERT ON IngredientSubstitution
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: IngredientSubstitution', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_ingredient_substitution_reopen_update AFTER UPDATE ON IngredientSubstitution
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: IngredientSubstitution', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL UNION SELECT NEW.recipe_version_id WHERE NEW.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_ingredient_substitution_reopen_delete AFTER DELETE ON IngredientSubstitution
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package relation changed: IngredientSubstitution', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeVersion
        WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT OLD.recipe_version_id WHERE OLD.recipe_version_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_stepingredient_reopen_insert AFTER INSERT ON StepIngredient
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package step relation changed: StepIngredient', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeStep
        WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = NEW.step_id)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = NEW.step_id) AND review_status='approved';
END;

CREATE TRIGGER trg_stepingredient_reopen_update AFTER UPDATE ON StepIngredient
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package step relation changed: StepIngredient', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeStep
        WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = OLD.step_id UNION SELECT recipe_version_id FROM RecipeStep WHERE step_id = NEW.step_id)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = OLD.step_id UNION SELECT recipe_version_id FROM RecipeStep WHERE step_id = NEW.step_id) AND review_status='approved';
END;

CREATE TRIGGER trg_stepingredient_reopen_delete AFTER DELETE ON StepIngredient
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package step relation changed: StepIngredient', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeStep
        WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = OLD.step_id)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = OLD.step_id) AND review_status='approved';
END;

CREATE TRIGGER trg_stepcookware_reopen_insert AFTER INSERT ON StepCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package step relation changed: StepCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeStep
        WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = NEW.step_id)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = NEW.step_id) AND review_status='approved';
END;

CREATE TRIGGER trg_stepcookware_reopen_update AFTER UPDATE ON StepCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package step relation changed: StepCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeStep
        WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = OLD.step_id UNION SELECT recipe_version_id FROM RecipeStep WHERE step_id = NEW.step_id)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = OLD.step_id UNION SELECT recipe_version_id FROM RecipeStep WHERE step_id = NEW.step_id) AND review_status='approved';
END;

CREATE TRIGGER trg_stepcookware_reopen_delete AFTER DELETE ON StepCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'recipe_version', item_id, 'recipe_version_package', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Package step relation changed: StepCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT recipe_version_id AS item_id FROM RecipeStep
        WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = OLD.step_id)
    )
    WHERE EXISTS (SELECT 1 FROM RecipeVersion p
                  WHERE p.recipe_version_id = item_id AND p.review_status = 'approved');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id IN (SELECT recipe_version_id FROM RecipeStep WHERE step_id = OLD.step_id) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencerecipe_reopen_insert AFTER INSERT ON ExperienceRecipe
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceRecipe', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencerecipe_reopen_update AFTER UPDATE ON ExperienceRecipe
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceRecipe', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL UNION SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL UNION SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencerecipe_reopen_delete AFTER DELETE ON ExperienceRecipe
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceRecipe', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencecookware_reopen_insert AFTER INSERT ON ExperienceCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencecookware_reopen_update AFTER UPDATE ON ExperienceCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL UNION SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL UNION SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencecookware_reopen_delete AFTER DELETE ON ExperienceCookware
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceCookware', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencemethod_reopen_insert AFTER INSERT ON ExperienceMethod
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceMethod', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencemethod_reopen_update AFTER UPDATE ON ExperienceMethod
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceMethod', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL UNION SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL UNION SELECT NEW.experience_id WHERE NEW.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_experiencemethod_reopen_delete AFTER DELETE ON ExperienceMethod
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    SELECT 'experience', item_id, 'experience', 'reopened',
           strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience applicability changed: ExperienceMethod', 'approved', 'needs_update'
    FROM (
        SELECT DISTINCT experience_id AS item_id FROM Experience
        WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL)
    )
    WHERE EXISTS (SELECT 1 FROM Experience p
                  WHERE p.experience_id = item_id AND p.review_status = 'approved');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id IN (SELECT OLD.experience_id WHERE OLD.experience_id IS NOT NULL) AND review_status='approved';
END;

CREATE TRIGGER trg_recipe_version_reopen_content_update
AFTER UPDATE OF servings, serving_unit, difficulty, prep_time_minutes, cook_time_minutes, change_note
ON RecipeVersion
WHEN OLD.review_status = 'approved'
 AND (NEW.servings IS NOT OLD.servings
   OR NEW.serving_unit IS NOT OLD.serving_unit
   OR NEW.difficulty IS NOT OLD.difficulty
   OR NEW.prep_time_minutes IS NOT OLD.prep_time_minutes
   OR NEW.cook_time_minutes IS NOT OLD.cook_time_minutes
   OR NEW.change_note IS NOT OLD.change_note)
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    VALUES ('recipe_version', OLD.recipe_version_id, 'recipe_version_package', 'reopened',
            strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Recipe-version package fields changed',
            'approved', 'needs_update');
    UPDATE RecipeVersion
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE recipe_version_id=OLD.recipe_version_id AND review_status='approved';
END;

CREATE TRIGGER trg_experience_reopen_content_update
AFTER UPDATE OF title, claim, conditions, exceptions, confidence_level, safety_impact
ON Experience
WHEN OLD.review_status = 'approved'
 AND (NEW.title IS NOT OLD.title
   OR NEW.claim IS NOT OLD.claim
   OR NEW.conditions IS NOT OLD.conditions
   OR NEW.exceptions IS NOT OLD.exceptions
   OR NEW.confidence_level IS NOT OLD.confidence_level
   OR NEW.safety_impact IS NOT OLD.safety_impact)
BEGIN
    INSERT INTO ReviewRecord
        (target_type, target_id, review_type, decision, reviewed_at, reason, previous_status, new_status)
    VALUES ('experience', OLD.experience_id, 'experience', 'reopened',
            strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'Experience content fields changed',
            'approved', 'needs_update');
    UPDATE Experience
       SET review_status='needs_update', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE experience_id=OLD.experience_id AND review_status='approved';
END;
