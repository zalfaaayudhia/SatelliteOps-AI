# Satellite Health Monitoring

## Purpose
Satellite health monitoring tracks telemetry values to identify potential anomalies and changes in spacecraft subsystem performance.

## Key telemetry indicators
Battery voltage, battery temperature, onboard computer status, and subsystem communication status are example indicators used in this demonstration.

## Anomaly handling
When a telemetry value falls outside its documented expected range, record the observation, check the relevant telemetry context, and escalate according to the applicable mission procedure. Do not assume a single unusual reading confirms a hardware failure.

## Incident records
Each incident record should include the observation time, subsystem, measured value, expected range if documented, and investigation status.