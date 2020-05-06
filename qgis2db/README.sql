/*
PROCEDURA DI INIZIALIZZAZIONE DEL DB PER CONFIGURAZIONE BASE DEL PROGETTO QGIS PER UTILIZZO PLUGIN PROGETTO_PNI.

ATTENZIONE! Il nuovo DB deve avere gia' abilitate le funzioni POSTGIS! Nonche' fornire i permessi di creazione all'utente/gruppo operatore_r: seguire le istruzioni delle righe successive.

NOTA BENE: Essendo alcune funzioni create a livello di DB e non piu' scritte nel codice del plugin stesso, se una di queste funzioni viene modificata, occorre aggiornarla MANUALMENTE su tutti i DB che utilizzano il plugin FTTH!!!
*/

-- Creare prima un database predisposto per PostGis. Da psql o da pgadmin:
CREATE DATABASE test_pni WITH ENCODING='UTF8' OWNER=postgres TEMPLATE=postgis_22_sample CONNECTION LIMIT=-1;
-- oppure direttamente da shell:
createdb -h localhost -p 5433 -U postgres -E UTF8 -template=postgis_22_sample -owner=postgres -e test_pni

-- Poi modificare i permessi sul DB appena creato:
GRANT CONNECT, TEMPORARY ON DATABASE "test_pni" TO public;
GRANT ALL ON DATABASE "test_pni" TO operatore_r;
GRANT CREATE ON DATABASE "test_pni" TO operatore_r;
GRANT SELECT ON TABLE public.spatial_ref_sys TO public;
GRANT SELECT ON TABLE public.spatial_ref_sys TO operatore_r;

-- oppure direttamente da shell:
psql -U postgres -d test_pni -p 5433 -h localhost -c 'GRANT CONNECT, TEMPORARY ON DATABASE "test_pni" TO public; GRANT ALL ON DATABASE "test_pni" TO postgres; GRANT CREATE ON DATABASE "test_pni" TO operatore_r;GRANT SELECT ON TABLE public.spatial_ref_sys TO public; GRANT SELECT, REFERENCES ON TABLE public.spatial_ref_sys TO operatore_r;'


--Creazione utente "operatore":
BEGIN;
DO
$body$
BEGIN
   IF NOT EXISTS (
      SELECT DISTINCT b.rolname rname FROM pg_auth_members a, pg_roles b WHERE a.roleid=b.oid AND b.rolname = 'operatore_r') THEN
      CREATE ROLE operatore_r NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;
   END IF;
   IF NOT EXISTS (
      SELECT * FROM pg_catalog.pg_user WHERE  usename = 'operatore') THEN
      CREATE ROLE operatore LOGIN ENCRYPTED PASSWORD 'operatore_2k16' NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;
      GRANT operatore_r TO operatore;
   END IF;
   IF NOT EXISTS (
      SELECT * FROM pg_catalog.pg_user WHERE  usename = 'sinergica') THEN
      CREATE ROLE sinergica LOGIN ENCRYPTED PASSWORD 'sinergica_2k19' NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;
      GRANT operatore_r TO sinergica;
	  GRANT ALL ON TABLE mappa_valori_pni2 TO sinergica;
   END IF;
END
$body$;
--CREATE ROLE operatore LOGIN ENCRYPTED PASSWORD 'operatore_2k16' NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;

CREATE TABLE tipo_progetti
(
  nomeschema character varying(32) NOT NULL,
  tipo_progetto character varying(6) NOT NULL,
  data_creazione timestamp without time zone DEFAULT now(),
  creator character varying(32),
  CONSTRAINT tipo_progetti_pkey PRIMARY KEY (nomeschema, tipo_progetto)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE tipo_progetti OWNER TO postgres;
GRANT ALL ON TABLE tipo_progetti TO postgres;
GRANT SELECT, INSERT ON TABLE tipo_progetti TO operatore_r;



SET role operatore;
CREATE SCHEMA IF NOT EXISTS lotto_base AUTHORIZATION operatore;
SET search_path = lotto_base, pg_catalog;
COMMIT;


--Modificare i permessi sulle tabelle topology per alcune operazioni del plugin:
GRANT ALL ON SCHEMA topology TO operatore;
GRANT ALL ON TABLE topology.topology_id_seq TO operatore;
GRANT ALL ON TABLE topology.layer TO operatore;
GRANT ALL ON TABLE topology.topology TO operatore;


--Modifica della funzione pgr_createtopology - da shell:
psql -U postgres -d <DB_NAME> -p 5432 -h <HOST> -f '<path>/correzione_funzione_pgrtopology.sql'

--oppure da PgAdmin, clic su Plugins/PSQL COnsole, e dalla console:
\i '<path>/correzione_funzione_pgrtopology.sql'

--oppure aprire il file e lanciarlo, come utente postgres.


/* COMPILAZIONE PLUGIN per RISORSE ESTERNE */
--aggiungere le evntuali risorse esterne (notoriamente immagini) nel file resources.qrc
--da riga di comando lanciare, dal percorso del plugin:
pyrcc4 -o resources.py resources.qrc

