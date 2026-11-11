#!/usr/bin/env bash
# The journal's timestamp: the PC's clock, in Paris time, to the minute ("2026-11-12 00:20"). Read, never estimated.
powershell -NoProfile -Command "[System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'Romance Standard Time').ToString('yyyy-MM-dd HH:mm')" | tr -d '\r'
