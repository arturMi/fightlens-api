-- The FightLens tables. This runs at every start; existing tables are left alone.

CREATE TABLE IF NOT EXISTS fighters (
    id          text PRIMARY KEY,  -- the id from ufcstats.com
    name        text NOT NULL,
    nickname    text,
    height_cm   integer,
    reach_cm    integer,
    weight_lbs  integer,
    stance      text,
    birth_date  date,
    -- Filled in after every import (see elo.py):
    division    text,
    wins        integer NOT NULL DEFAULT 0,
    losses      integer NOT NULL DEFAULT 0,
    draws       integer NOT NULL DEFAULT 0,
    elo         real,
    last_fight  date
);

CREATE TABLE IF NOT EXISTS events (
    id       text PRIMARY KEY,
    name     text NOT NULL,
    date     date NOT NULL,
    location text
);

CREATE TABLE IF NOT EXISTS fights (
    id          text PRIMARY KEY,
    event_id    text NOT NULL REFERENCES events (id),
    bout_order  integer NOT NULL,              -- 0 = main event, which is fought last
    fighter1_id text REFERENCES fighters (id), -- empty if the name could not be matched
    fighter1    text NOT NULL,
    fighter2_id text REFERENCES fighters (id),
    fighter2    text NOT NULL,
    result      text NOT NULL,                 -- 'fighter1', 'fighter2', 'draw' or 'no contest'
    method      text NOT NULL,                 -- for example 'KO/TKO' or 'Submission'
    round       integer,
    time        text,
    division    text,
    title_fight boolean NOT NULL,
    elo1_before real,
    elo1_after  real,
    elo2_before real,
    elo2_after  real,
    published   boolean NOT NULL DEFAULT false -- already sent to the Redis Stream?
);
