// CoreIOT/ThingsBoard Script Filter, JavaScript mode.
// Outputs: True -> Create Alarm; False -> Clear-condition filter.
return Number(msg.temperature) >= 32 || Number(msg.humidity) >= 80 || msg.anomaly === true;
