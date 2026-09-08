import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir:'tests/e2e',testMatch:'studio.spec.ts',timeout:90000,workers:1,
  use:{...devices['iPhone 13'],baseURL:'http://localhost:5173',browserName:'webkit',
    screenshot:'only-on-failure',trace:'retain-on-failure'},
});
