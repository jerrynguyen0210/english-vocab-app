module.exports = {
  preset: 'jest-expo',
  testMatch: ['<rootDir>/tests/components/**/*.test.tsx'],
  moduleNameMapper: {
    '\\.css$': '<rootDir>/tests/components/style-mock.cjs',
    '^@/assets/(.*)$': '<rootDir>/assets/$1',
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  setupFilesAfterEnv: ['<rootDir>/tests/components/setup.tsx'],
};
