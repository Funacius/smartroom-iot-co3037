// Hysteresis: intermediate readings must NOT clear an active alarm.
return Number(msg.temperature) <= 30 && Number(msg.humidity) <= 75 && msg.anomaly !== true;
