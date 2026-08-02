import { deviceDisplayName, isOnline, relativeTime } from '@/lib/utils';

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
