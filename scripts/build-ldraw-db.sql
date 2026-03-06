-- SQLite schema for LDraw parts and models database

-- Categories from the official LDraw website
-- CREATE TABLE CATEGORIES (category VARCHAR PRIMARY KEY); 

-- Colors from the official LDraw library, LDrawConfig.ldr (?)
CREATE TABLE COLORS (code VARCHAR PRIMARY KEY, color VARCHAR, value VARCHAR); 

-- Model info inferred by an AI vision model from model image renderings
CREATE TABLE MODEL_AI_CAT_DESC_KWS (alias VARCHAR PRIMARY KEY, category VARCHAR, description VARCHAR, keywords VARCHAR);

-- Models DISTINCT categories
CREATE TABLE MODEL_AI_CATS_UNIQ (category VARCHAR PRIMARY KEY);

-- Models DISTINCT keywords
CREATE TABLE MODEL_AI_KWS_UNIQ (keyword VARCHAR PRIMARY KEY);

-- Model categories extracted from 0 !CATEGORY lines in model files
-- CREATE TABLE MODEL_CATEGORIES (alias VARCHAR PRIMARY KEY, categories VARCHAR);

-- Model keywords extracted from 0 !KEYWORD lines in model files
-- CREATE TABLE MODEL_KEYWORDS (alias VARCHAR PRIMARY KEY, keywords VARCHAR); 

-- Model num parts and estimated difficulty
CREATE TABLE MODEL_NUM_PARTS (alias VARCHAR PRIMARY KEY, num_parts INTEGER, difficulty INTEGER); 

-- Model file sizes in bytes and KB
CREATE TABLE MODEL_SIZES (alias VARCHAR PRIMARY KEY, size INTEGER, size_kb INTEGER); 

-- Model submodels extracted from 0 !FILE lines in model files
CREATE TABLE MODEL_SUBMODELS (alias VARCHAR, submodel VARCHAR);

-- Model themes extracted from 0 !THEME lines in model files
-- CREATE TABLE MODEL_THEMES (alias VARCHAR PRIMARY KEY, themes VARCHAR); 

-- Computed bounding boxes for parts
CREATE TABLE PART_BBOXES (
    alias VARCHAR PRIMARY KEY, 
    min_x REAL, 
    min_y REAL, 
    min_z REAL, 
    max_x REAL, 
    max_y REAL, 
    max_z REAL, 
    center_x REAL, 
    center_y REAL, 
    center_z REAL, 
    dim_x REAL, 
    dim_y REAL, 
    dim_z REAL, 
    diag REAL, 
    complete BOOLEAN);

-- Part categories extracted from 0 !CATEGORY lines in part files
CREATE TABLE PART_CATEGORIES (alias VARCHAR PRIMARY KEY, categories VARCHAR);

-- Part infos from lark parsing part files
CREATE TABLE PART_INFOS (alias VARCHAR PRIMARY KEY, name VARCHAR, description TEXT);

-- Part keywords extracted from 0 !KEYWORD lines in part files
CREATE TABLE PART_KEYWORDS (alias VARCHAR PRIMARY KEY, keywords VARCHAR);

-- Selected models, **all views will be filtered by these**
CREATE TABLE MODELS (alias VARCHAR PRIMARY KEY);

-- A view to aggregate and filter by MODELS all the info about models for easier querying
CREATE VIEW VW_MODEL_INFOS AS SELECT 
    m.alias AS alias,
    mai.category AS category,
    mai.description AS description,
    mai.keywords AS keywords,
    mnp.num_parts AS num_parts,
    mnp.difficulty AS difficulty,
    s.size_kb AS size_kb
FROM 
    MODELS m
INNER JOIN
    MODEL_AI_CAT_DESC_KWS mai ON m.alias = mai.alias
INNER JOIN 
    MODEL_NUM_PARTS mnp ON m.alias = mnp.alias
INNER JOIN 
    MODEL_SIZES s ON m.alias = s.alias;

-- A view to aggregate model submodels for easier querying
CREATE VIEW VW_MODEL_SUBMODELS AS SELECT 
    m.alias AS alias,
    ms.submodel AS submodel
FROM 
    MODELS m
INNER JOIN
    MODEL_SUBMODELS ms ON m.alias = ms.alias;

-- A view to aggregate and filter parts
CREATE VIEW VW_PART_INFOS_BBOXES AS SELECT 
    pi.alias AS alias, 
    pi.name AS name, 
    pi.description AS description,
    pb.dim_x AS dim_x, 
    pb.dim_y AS dim_y, 
    pb.dim_z AS dim_z
FROM 
    PART_INFOS pi
INNER JOIN
    PART_BBOXES pb ON pi.alias = pb.alias;

-- Equivalences with external catalogs
-- CREATE TABLE PARTS_BRICKLINK_CAT (alias VARCHAR PRIMARY KEY, catalog_part_num VARCHAR); 

-- CREATE TABLE PARTS_REBRICKABLE_CAT (alias VARCHAR PRIMARY KEY, catalog_part_num VARCHAR); 
