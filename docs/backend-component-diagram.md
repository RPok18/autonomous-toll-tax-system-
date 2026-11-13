# Backend Component Diagram

The diagram shows the implemented backend boundaries. The API and offline
simulation are separate execution paths; the ANPR pipeline is implemented as a
swappable component but is not currently connected to either path.

```mermaid
flowchart TB
    operators["Operators / dashboard users"]
    sensors["Lane sensors / devices"]

    subgraph backend["Backend (FastAPI application)"]
        app["Application entry point<br/>health check · startup · static dashboard"]
        dashboard["Dashboard static files"]

        subgraph api["HTTP API"]
            routers["API routers<br/>auth · vehicles · transactions<br/>devices · plazas · exceptions"]
            schemas["Pydantic request / response schemas"]
            auth["Authentication and authorization<br/>JWT · role-based access"]
            audit["Audit logging"]
        end

        subgraph domain["API domain services"]
            toll["Toll calculator<br/>tariff lookup · fare · discounts · surcharges"]
            config["Application settings"]
        end

        subgraph persistence["Persistence"]
            dbaccess["SQLAlchemy engine and session"]
            models["ORM models<br/>vehicles · trips · plazas · tariffs<br/>transactions · users · exceptions · audit"]
        end

        subgraph sensor_components["Sensor-processing components (not API-wired)"]
            anpr["ANPR pipeline<br/>image preprocessing · plate detection · OCR"]
            anpr_impl["Detector / OCR implementations<br/>text-band or YOLO · Tesseract"]
            rfid["RFID reader interface"]
        end

        subgraph simulation["Offline simulation (separate runner)"]
            runner["Simulation runner"]
            anpr_sim["ANPR simulator"]
            rfid_sim["RFID simulator"]
            fusion["Fusion engine"]
            policy["Policy engine<br/>YAML-based simulated toll rules"]
            metrics["Metrics and reports"]
            csv["CSV export"]
        end
    end

    postgres[("PostgreSQL")]
    plate_files[("Plate-capture file volume")]

    operators -->|"HTTP"| app
    app --> routers
    app --> dashboard
    routers --> schemas
    routers --> auth
    routers --> audit
    routers --> toll
    routers --> dbaccess
    auth --> dbaccess
    audit --> dbaccess
    toll --> dbaccess
    routers --> config
    dbaccess --> models
    dbaccess -->|"SQLAlchemy / psycopg"| postgres
    runner -.->|"optional, marked demo records"| dbaccess
    routers -->|"plate-image access"| plate_files

    anpr --> anpr_impl
    anpr -.->|"signal contract only; not connected"| fusion
    rfid -.->|"reader contract only; not connected"| fusion
    sensors -.->|"not currently wired"| anpr
    sensors -.->|"not currently wired"| rfid
    runner --> anpr_sim
    runner --> rfid_sim
    anpr_sim --> fusion
    rfid_sim --> fusion
    fusion --> policy
    runner --> policy
    runner --> metrics
    metrics --> csv
```

## Reading the diagram

- The FastAPI application exposes the API and serves the dashboard's static
  files. API routers validate payloads with Pydantic schemas and use shared
  authentication, authorization, auditing, and database components.
- Vehicle toll charging uses the toll calculator and persisted vehicle,
  plaza, trip, tariff, and transaction data. The toll calculator currently
  reads database tariffs; the YAML policy engine shown below belongs to the
  separate simulation path.
- The simulation runner uses simulated ANPR and RFID reads, combines them in
  the fusion engine, and evaluates simulated toll rules. By default it writes
  metrics and reports through CSV export without touching the API database.
  An explicit persistence option can add clearly marked demo transactions
  and exceptions to the database; it does not change vehicle balances.
- The ANPR pipeline and RFID reader interfaces exist as backend components,
  but live lane sensor integration and API processing are not currently
  wired up.
