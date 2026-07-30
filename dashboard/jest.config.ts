import type { Config } from 'jest';

const config: Config = {
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

export default config;
