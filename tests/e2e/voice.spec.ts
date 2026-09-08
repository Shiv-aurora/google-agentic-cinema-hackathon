import { test, expect } from '@playwright/test';
import path from 'node:path';

test.use({permissions:['microphone'],launchOptions:{args:[
  '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
  `--use-file-for-fake-audio-capture=${path.resolve('data/voice-fixtures/roll.wav')}`,
]}});

test('virtual microphone recording rolls real cameras through Google speech',async({page})=>{
  test.skip(process.env.CLAPPY_TEST_VOICE!=='1','Opt in to the real paid Google speech test.');
  await page.goto('/');
  await page.getByRole('button',{name:'Arm cameras',exact:true}).click();
  await expect(page.getByRole('button',{name:'Roll cameras',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Speak a direction',exact:true}).click();
  await expect(page.getByRole('button',{name:'Send direction',exact:true})).toBeVisible();
  // Capture the actual spoken phrase from the paced virtual microphone device.
  await page.waitForTimeout(3500);
  await page.getByRole('button',{name:'Send direction',exact:true}).click();
  await expect(page.getByRole('button',{name:'Cut',exact:true})).toBeEnabled({timeout:35000});
  await expect(page.locator('.voice-control')).toContainText(/Heard:.*Roll/i);
  await page.screenshot({path:'artifacts/studio-voice-roll.png',fullPage:true});
  await page.getByRole('button',{name:'Cut',exact:true}).click();
  await expect(page.locator('.review-player video')).toBeVisible({timeout:30000});
});
