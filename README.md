# Groundwater_depletion_detection_system

To run(inside /Ground_water):
> python main.py synthetic

## Run with Docker (one command)

```bash
docker compose up --build
```

Then open http://localhost:8000 (dashboard) and http://localhost:8000/admin.

The container starts in the offline **synthetic** benchmark mode. For live
Earth Engine mode, run `earthengine authenticate` on the host once, set your
project id, and start with:

```bash
GEE_PROJECT_ID=<your-project> GW_MODE=realtime docker compose up --build
```

The sampled Earth Engine rasters are cached in `./cache` (mounted volume),
so reopening the same region is fast after the first live build. Admin UI
settings persist in `./data/ui_settings.json`.

Without Docker, the classic route still works:

```bash
pip install -r requirements.txt
python main.py synthetic
```

## Run the tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## Live field sensors (ThingSpeak)

The dashboard's Predictions tab carries a **Live Field Sensors** panel fed
by the borewell IoT rig's ThingSpeak channel (temperature, humidity, soil
moisture, water level, discharge flow), and the PDF report can include the
same readings ("Field Sensor Readings" option in the Generate PDF pop-up).

The ThingSpeak read key stays on the server — set it in `.env` (never in
code, never in the browser):

```bash
THINGSPEAK_CHANNEL_ID=3575415
THINGSPEAK_READ_KEY=<your ThingSpeak read API key>
```

Restart the server after editing `.env`. Without the key, the panel shows
a "not configured" notice and reports simply omit the sensor block.
