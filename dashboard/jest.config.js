// Jest configuration — plain JS to avoid requiring ts-node in CI.
// (ts-jest handles TypeScript test files; only this config file is JS.)
/** @type {import('jest').Config} */
const config = {
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/src'],
  testMatch: [
    '**/__tests__/**/*.test.{ts,tsx}',
  ],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {
      tsconfig: {
        jsx: 'react-jsx',
        esModuleInterop: true,
      },
    }],
  },
  moduleNameMapper: {
    '@/(.*)': '<rootDir>/src/$1',
  },
};

module.exports = config;
