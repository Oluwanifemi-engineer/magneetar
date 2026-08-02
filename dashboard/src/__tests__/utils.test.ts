import { deviceDisplayName, isOnline, relativeTime, parseTimestamp, formatTimestamp, locationTimestamp } from '@/lib/utils';

describe('deviceDisplayName', () => {
  it('prefers the owner-set alias', () => {
    expect(deviceDisplayName({ alias: 'My Galaxy', model: 'SM-A037F' })).toBe('My Galaxy');
  });

  it('falls back to the registered model instead of a generic label', () => {
    expect(deviceDisplayName({ alias: null, model: 'Samsung SM-A037F' })).toBe('Samsung SM-A037F');
    expect(deviceDisplayName({ alias: '', model: 'Pixel 8' })).toBe('Pixel 8');
  });

  it('uses a generic label only when nothing else is known', () => {
    expect(deviceDisplayName({ alias: null, model: null })).toBe('Device');
    expect(deviceDisplayName(null)).toBe('Device');
    expect(deviceDisplayName(undefined)).toBe('Device');
  });

  it('treats whitespace-only aliases as unset', () => {
    expect(deviceDisplayName({ alias: '   ', model: 'SM-A037F' })).toBe('SM-A037F');
  });
});

describe('relativeTime', () => {
  it('returns Never for missing timestamps', () => {
    expect(relativeTime(null)).toBe('Never');
    expect(relativeTime(undefined)).toBe('Never');
    expect(relativeTime('')).toBe('Never');
  });
});

describe('isOnline', () => {
  it('is false without a timestamp', () => {
    expect(isOnline(null)).toBe(false);
  });

  it('respects the freshness threshold', () => {
    const now = new Date().toISOString();
    const fiveMinAgo = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(isOnline(now)).toBe(true);
    expect(isOnline(fiveMinAgo)).toBe(false);
    expect(isOnline(fiveMinAgo, 10 * 60_000)).toBe(true);
  });
});

describe('parseTimestamp — trail replay invalid-date regression', () => {
  it('parses ISO-8601 with offset', () => {
    const d = parseTimestamp('2026-08-02T10:00:00.123456+00:00');
    expect(d).not.toBeNull();
  });

  it('parses SQLite space-separated timestamps (Safari-safe)', () => {
    const d = parseTimestamp('2026-08-01 20:34:00');
    expect(d).not.toBeNull();
    expect(d!.toISOString()).toBe('2026-08-01T20:34:00.000Z');
  });

  it('returns null instead of Invalid Date for junk input', () => {
    expect(parseTimestamp(undefined)).toBeNull();
    expect(parseTimestamp(null)).toBeNull();
    expect(parseTimestamp('')).toBeNull();
    expect(parseTimestamp('not-a-date')).toBeNull();
  });
});

describe('locationTimestamp — no more Invalid Date in Trail Replay', () => {
  it('prefers server_timestamp, then device_timestamp, then timestamp', () => {
    expect(locationTimestamp({ server_timestamp: 'A', device_timestamp: 'B', timestamp: 'C' })).toBe('A');
    expect(locationTimestamp({ device_timestamp: 'B', timestamp: 'C' })).toBe('B');
    expect(locationTimestamp({ timestamp: 'C' })).toBe('C');
  });

  it('handles location rows that only carry server_timestamp (the actual server shape)', () => {
    expect(locationTimestamp({ server_timestamp: '2026-08-02T10:00:00+00:00' })).toBe('2026-08-02T10:00:00+00:00');
  });

  it('returns null for empty rows', () => {
    expect(locationTimestamp(null)).toBeNull();
    expect(locationTimestamp(undefined)).toBeNull();
    expect(locationTimestamp({})).toBeNull();
  });
});

describe('formatTimestamp', () => {
  it('never renders Invalid Date — falls back to an em dash', () => {
    expect(formatTimestamp(undefined)).toBe('—');
    expect(formatTimestamp(null)).toBe('—');
    expect(formatTimestamp('garbage')).toBe('—');
  });

  it('formats a valid timestamp (human-readable, not Invalid Date)', () => {
    const out = formatTimestamp('2026-08-01 20:34:00');
    expect(out).not.toBe('—');
    expect(out).toContain('34:00');
  });
});
