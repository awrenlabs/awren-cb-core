CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type);
