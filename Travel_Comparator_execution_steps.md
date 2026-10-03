# Travel Weather Comparator (A2A) — Step-by-Step Guide

Compare multiple US cities and find the best travel destination by negotiating between a **Weather Agent** (real NWS data via MCP) and a **Travel Advisor Agent** (flight costs, hotels, events).

---

## How It Works

```
User: "Compare Austin, Miami, Denver for a trip from NYC"
                    │
                    ▼
         Travel Coordinator (OpenAI)
          │                      │
          │ A2A (:5001)          │ A2A (:5003)
          ▼                      ▼
    Weather Agent          Travel Advisor Agent
          │                      │
          │ MCP (stdio)          │ travel_data.json
          ▼                      │
    weather_server.py            │
    (NWS: alerts + forecast)     (flights, hotels, events)
```

&nbsp;

### 3-Round Negotiation

| Round | What Happens |
| :---- | :---- |
| **1** | Parallel fan-out: weather for each city \+ travel costs for all cities |
| **2** | Coordinator detects conflicts (best weather \!= cheapest, events inflating prices, dangerous weather) and sends adjusted tasks |
| **3** | Coordinator synthesizes a final recommendation with comparison table |

&nbsp;

---

## Prerequisites

- Python 3.10+  
- `uv` installed  
- OpenAI API key  
- `weather-skills/` server set up (from the Skills demo)  
- `a2a-event-planner/` dependencies installed (from the Event Planner demo)

If you already ran the A2A Event Planner demo, the environment is ready. If not, follow Step 1 below.

---

## Step 1: Environment Setup (skip if already done)

### 1.1 Set up the MCP Weather Server

```sh
cd /path/to/MCP/weather-skills
uv venv
source .venv/bin/activate
uv add "mcp[cli]" httpx
deactivate
```

&nbsp;

### 1.2 Set up the A2A Event Planner environment

```sh
cd /path/to/MCP/a2a-event-planner
uv venv
source .venv/bin/activate
uv add fastapi uvicorn httpx mcp openai python-dotenv
```

&nbsp;

### 1.3 Configure OpenAI API key

```sh
cp .env.example .env
```

&nbsp;

Edit `.env`:

```
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

&nbsp;

---

## Step 2: Start the Agents (3 Terminals)

Open **three separate terminal windows**. Each must `cd` into `a2a-event-planner/` and activate the venv.

### Terminal 1 — Weather Agent (port 5001\)

```sh
cd /path/to/MCP/a2a-event-planner
source .venv/bin/activate
uv run weather_agent.py /absolute/path/to/MCP/weather-skills/weather_server.py
```

&nbsp;

Expected:

```
Weather Agent starting...
  Connecting to MCP server: /path/to/weather-skills/weather_server.py
  MCP connected — tools: ['get_alerts', 'get_forecast']
  Weather Agent ready on http://localhost:5001
INFO:     Uvicorn running on http://0.0.0.0:5001
```

&nbsp;

### Terminal 2 — Travel Advisor Agent (port 5003\)

```sh
cd /path/to/MCP/a2a-event-planner
source .venv/bin/activate
uv run travel_agent.py
```

&nbsp;

Expected:

```
Travel Advisor Agent starting...
  Loaded 8 cities from travel_data.json
  Travel Advisor Agent ready on http://localhost:5003
INFO:     Uvicorn running on http://0.0.0.0:5003
```

&nbsp;

### Terminal 3 — Travel Coordinator

```sh
cd /path/to/MCP/a2a-event-planner
source .venv/bin/activate
uv run travel_coordinator.py
```

&nbsp;

Expected:

```
====================================================
  A2A Travel Weather Comparator — Coordinator
====================================================

  Agents expected:
    Weather Agent        → localhost:5001
    Travel Advisor Agent → localhost:5003

  Example queries:
    Compare Austin, Miami, Denver for a trip from NYC
    Best city to visit from Chicago: Nashville, Phoenix, or Seattle?
    Budget trip from LA to Denver, Phoenix, or Austin next week

  Type 'quit' to exit.

Query:
```

&nbsp;

---

## Step 3: Verify Agent Discovery

Before running a negotiation, confirm the agents are reachable.

In a **fourth terminal** (or use the browser):

```sh
curl -s http://localhost:5001/.well-known/agent.json | python -m json.tool
```

&nbsp;

Expected: Weather Agent card with name, description, skills.

```sh
curl -s http://localhost:5003/.well-known/agent.json | python -m json.tool
```

&nbsp;

Expected: Travel Advisor Agent card with `compare_travel_costs` and `check_events_impact` skills.

---

## Step 4: Run the Travel Comparison

### 4.1 Basic 3-city comparison

In the Coordinator (Terminal 3):

```
Query: Compare Austin, Miami, and Denver for a 5-day trip from New York
```

&nbsp;

**What you'll see in Terminal 3 (Coordinator):**

```
====================================================
       A2A TRAVEL WEATHER COMPARATOR
====================================================

[Discovery] Contacting agents...
  Weather Agent:  Weather Agent (http://localhost:5001)
    - Weather Assessment: Evaluate weather conditions for a location...
  Travel Agent:   Travel Advisor Agent (http://localhost:5003)
    - Travel Cost Comparison: Compare flight, hotel, and total trip c...
    - Event Impact Check: Check if upcoming events or festivals in a ...

[Parse] Extracting travel parameters...
  Cities:    Austin TX, Miami FL, Denver CO
  Origin:    New York
  Dates:     next week
  Duration:  5 days

----------------------------------------------------
  ROUND 1: Initial Parallel Assessment
----------------------------------------------------
  Sending 3 weather tasks + 1 travel task in parallel...

  Weather Results:
    Austin: CAUTION (high: 98F)
      - High temperature: 98F — heat risk
    Miami: GO (high: 84F)
    Denver: GO (high: 72F)

  Travel Cost Results:
    #1 Denver: $900.0 total (flight $250 + hotel $130/night x 5d)
    #2 Austin: $1030.0 total (flight $280 + hotel $150/night x 5d)
    #3 Miami: $1665.0 total (flight $180 + hotel $297/night x 5d)
       EVENT: Miami Music Week / Ultra (March 17-23): Massive EDM...

----------------------------------------------------
  ROUND 2: Conflict Detection & Resolution
----------------------------------------------------
  Analyzing weather vs travel data for conflicts...

  CONFLICTS FOUND:
    - Miami has best flight price but highest total due to peak season + events
    - Austin has heat concerns (CAUTION)
  Best weather: Denver  |  Best value: Denver
  Explanation: Denver has best weather AND lowest total cost...

  Sending 2 adjusted task(s)...
    Weather (adjusted) Austin: CAUTION
    Events Miami: avoid (impact: severe — expect 2-3x hotel pricing)

----------------------------------------------------
  ROUND 3: Final Synthesis
----------------------------------------------------
  Generating final travel recommendation...

====================================================
## Travel Recommendation

### Winner: Denver, CO
Denver offers the best combination of pleasant weather (72F, clear skies,
no active alerts) and lowest total trip cost ($900 for 5 days). ...

### Comparison Table
| City    | Weather | High | Alerts | Flight | Hotel/N | Total  | Time  | Events       |
|---------|---------|------|--------|--------|---------|--------|-------|--------------|
| Denver  | GO      | 72F  | None   | $250   | $130    | $900   | 4.5h  | None         |
| Austin  | CAUTION | 98F  | Heat   | $280   | $150    | $1,030 | 3.5h  | None         |
| Miami   | GO      | 84F  | None   | $180   | $297    | $1,665 | 3.0h  | Music Week   |

### City-by-City Breakdown
**Denver** ...
**Austin** ...
**Miami** ...

### Negotiation Summary
Round 1: Weather Agent reported Denver GO, Austin CAUTION (heat), Miami GO.
Travel Agent reported Denver cheapest at $900, Miami most expensive at $1,665
due to peak season 35% surcharge. ...
====================================================
```

&nbsp;

**Terminal 1 (Weather Agent)** shows MCP tool calls:

```
  Task a1b2c3d4... | get_alerts(state=TX)
  Task a1b2c3d4... | get_forecast(lat=30.2672, lon=-97.7431)
  Task a1b2c3d4... | recommendation=CAUTION
  Task e5f6g7h8... | get_alerts(state=FL)
  Task e5f6g7h8... | get_forecast(lat=25.7617, lon=-80.1918)
  Task e5f6g7h8... | recommendation=GO
  Task i9j0k1l2... | get_alerts(state=CO)
  Task i9j0k1l2... | get_forecast(lat=39.7392, lon=-104.9903)
  Task i9j0k1l2... | recommendation=GO
```

&nbsp;

**Terminal 2 (Travel Agent)** shows cost calculations:

```
  Task m3n4o5p6... | action=compare_travel_costs
  Task m3n4o5p6... | compared 3 cities, cheapest=Denver
  Task q7r8s9t0... | action=check_events_impact
  Task q7r8s9t0... | city=Miami events_recommendation=avoid
```

&nbsp;

---

### 4.2 Budget-focused comparison

```
Query: Budget trip from Chicago: Nashville, Phoenix, or New Orleans?
```

&nbsp;

This tests:

- Different origin city (Chicago)  
- Phoenix peak season surcharge  
- New Orleans event check (Mardi Gras / Jazz Fest)

### 4.3 West coast comparison

```
Query: Best city from LA for a week: San Francisco, Seattle, or Phoenix?
```

&nbsp;

This tests:

- San Francisco's high hotel costs \+ GDC conference impact  
- Seattle's mild but rainy weather  
- Phoenix's proximity to LA (cheap flights) vs heat

### 4.4 Event conflict scenario

```
Query: Compare Austin and Nashville from Atlanta, mid-March trip
```

&nbsp;

This tests:

- Austin SXSW (March 7-15) driving up prices  
- Nashville as a likely winner due to no events \+ cheap flights from Atlanta

### 4.5 Four-city wide comparison

```
Query: Compare Miami, Denver, San Francisco, and New Orleans from New York for 7 days
```

&nbsp;

This tests:

- 4 parallel weather tasks  
- Multiple event conflicts (Miami Music Week, GDC, possible Mardi Gras)  
- Peak season surcharges  
- Larger comparison table in synthesis

---

## Step 5: Understanding the Negotiation

### What Makes This A2A (Not Just Parallel API Calls)

1. **Agent Discovery** — The coordinator doesn't hardcode what agents can do. It reads Agent Cards dynamically. If the Travel Agent added a new skill tomorrow, the coordinator would discover it.

2. **Conflict-Driven Rounds** — Round 2 only fires when agents disagree. If weather and cost both point to the same city, Round 2 says "no conflicts" and skips directly to synthesis. The conversation between agents is conditional, not scripted.

3. **Cross-Agent Constraint Passing** — Weather Agent's concerns (e.g., "Austin is too hot") become constraints for the Travel Agent (e.g., "recheck events to see if cost justifies the heat risk"). This is negotiation — one agent's output reshapes another agent's task.

4. **MCP Inside A2A** — The Weather Agent is an A2A agent externally but an MCP client internally. The Travel Coordinator never touches MCP. The Weather Agent bridges the two protocols:

```
A2A request           MCP tool calls
Coordinator ───→ Weather Agent ───→ weather_server.py
  (HTTP)           (stdio)          get_alerts()
                                    get_forecast()
```

&nbsp;

### Comparison: MCP Skill vs A2A Negotiation

The `multi_day_trip_planner` MCP Skill (from the Skills demo) does city comparison too. Here's why A2A adds value:

|  | MCP Skill | A2A Travel Comparator |
| :---- | :---- | :---- |
| Weather data | Yes | Yes (same MCP server) |
| Cost data | No | Yes (Travel Agent) |
| Event impact | No | Yes (Travel Agent) |
| Parallel execution | No (LLM calls tools one by one) | Yes (asyncio.gather) |
| Conflict resolution | No (LLM decides alone) | Yes (agents negotiate) |
| New data sources | Requires editing server | Add a new agent |

&nbsp;

---

## Available Cities in Travel Database

| City | State | Peak Season | Notable Events |
| :---- | :---- | :---- | :---- |
| Austin | TX | No | SXSW (March), Food & Wine (April) |
| Miami | FL | Yes (+35%) | Music Week/Ultra (March), Miami Open (March) |
| Denver | CO | No | St. Patrick's Parade (March) |
| San Francisco | CA | No | GDC (March) |
| Nashville | TN | No | CMA Music Fest (June) |
| Seattle | WA | No | Cherry Blossom (April) |
| Phoenix | AZ | Yes (+20%) | Spring Training (Feb-March) |
| New Orleans | LA | No | Mardi Gras (Feb-March), Jazz Fest (April-May) |

&nbsp;

**Origin cities with flight data:** New York, Los Angeles, Chicago, Dallas, Atlanta

---

## Troubleshooting

| Issue | Solution |
| :---- | :---- |
| `Connection refused` on :5001 | Start Weather Agent first (Terminal 1\) |
| `Connection refused` on :5003 | Start Travel Agent (Terminal 2\) |
| `ModuleNotFoundError: a2a_protocol` | Run from `a2a-event-planner/` directory |
| Weather Agent MCP connection fails | Use absolute path to `weather_server.py` |
| City not found in travel data | Use exact city names from the table above |
| OpenAI JSON parse error | Retry — occasional LLM formatting issue |
| `Address already in use` | Kill existing process: `lsof -ti:5001 | xargs kill` |
| Travel Agent returns no data for origin | Use one of the 5 origin cities listed above |

&nbsp;

---

## Cleanup

```
Terminal 3: Type 'quit' at the Query prompt
Terminal 1: Ctrl+C to stop Weather Agent
Terminal 2: Ctrl+C to stop Travel Advisor Agent
```

&nbsp;

---

## Project Structure (After This Demo)

```
MCP/
├── Travel_steps.md                   # This guide
├── Travel_Comparator_Design.md       # Algorithm design document
│
├── a2a-event-planner/                # A2A agents and coordinators
│   ├── a2a_protocol.py               # Shared A2A types
│   ├── weather_agent.py              # A2A Weather Agent (:5001) → MCP
│   ├── venue_agent.py                # A2A Venue Agent (:5002) — event planner
│   ├── coordinator.py                # Event Planner coordinator
│   ├── venue_data.json               # Venue database
│   ├── travel_agent.py               # A2A Travel Advisor Agent (:5003) — NEW
│   ├── travel_coordinator.py         # Travel Comparator coordinator — NEW
│   ├── travel_data.json              # Flight/hotel/event database — NEW
│   ├── .env.example
│   └── pyproject.toml
│
├── weather-skills/                   # MCP server
│   ├── weather_server.py
│   ├── state_codes.json
│   └── pyproject.toml
```

&nbsp;