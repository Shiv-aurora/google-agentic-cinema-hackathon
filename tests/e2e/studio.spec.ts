import { test, expect } from '@playwright/test';

test('real cameras roll, stream, switch, stop and produce reviewable video', async ({page})=>{
  const errors:string[]=[];page.on('pageerror', error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Arm cameras'})).toBeEnabled();
  await page.getByRole('button',{name:'Arm cameras'}).click();
  await expect(page.getByRole('button',{name:'Roll cameras'})).toBeEnabled();
  await page.getByRole('button',{name:'Roll cameras'}).click();
  await expect(page.getByRole('button',{name:'Cut',exact:true})).toBeEnabled({timeout:20000});
  await expect(page.locator('.rec-label')).toHaveCount(3);
  // Inspect decoded frames in the actual MediaMTX player, not just an iframe URL.
  const program=page.locator('.program-layer.visible iframe');
  const video=program.contentFrame().locator('video');
  await expect(video).toBeVisible({timeout:15000});
  await expect.poll(()=>video.evaluate((v:HTMLVideoElement)=>v.videoWidth),{timeout:15000}).toBeGreaterThan(0);
  const first=await video.evaluate((v:HTMLVideoElement)=>v.currentTime);
  await expect.poll(()=>video.evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeGreaterThan(first+.3);
  await page.screenshot({path:'artifacts/studio-live.png',fullPage:true});
  await page.getByRole('button',{name:'Cut to Tom',exact:true}).click();
  await expect(page.locator('.program-overlay')).toContainText('Tom');
  await expect(page.locator('.decision-hud')).toContainText('You directed');
  await expect(page.locator('.decision-hud')).toContainText('Manual director selection');
  await page.getByRole('button',{name:'Cut to Bella',exact:true}).click();
  await expect(page.locator('.program-overlay')).toContainText('Bella');
  await expect(page.getByRole('button',{name:/Use my style/})).toBeVisible();
  await page.getByRole('button',{name:'Cut',exact:true}).click();
  await expect(page.locator('.review-player video')).toBeVisible({timeout:30000});
  await expect(page.getByText('One performance. Three films.')).toBeVisible();
  await expect(page.getByRole('button',{name:/Create three cuts/})).toBeVisible();
  await expect(page.getByText('3 independent recordings verified')).toBeVisible();
  await expect(page.getByRole('link',{name:'OTIO timeline'})).toBeVisible();
  await page.locator('.review-player video').evaluate((v:HTMLVideoElement)=>v.play());
  await expect.poll(()=>page.locator('.review-player video').evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeGreaterThan(.2);
  await page.screenshot({path:'artifacts/studio-review.png',fullPage:true});
  await page.reload();
  await page.getByRole('button',{name:/Takes & edits/}).click();
  await expect(page.locator('.review-player video')).toBeVisible();
  if(process.env.CLAPPY_TEST_AI==='1'){
    const before=await page.locator('.review-player video').getAttribute('src');
    await page.getByLabel('Director note').fill('Create a Bella-focused version. Give camera b at least 75% of the whole take, including the ending. Keep the complete duration.');
    await page.getByRole('button',{name:'Create another edit'}).click();
    await expect(page.locator('.agent-response')).toBeVisible();
    await expect(page.locator('.edit-actions>div').first().getByRole('button')).toHaveCount(2,{timeout:70000});
    await page.locator('.edit-actions>div').first().getByRole('button').nth(1).click();
    await expect(page.locator('.review-player video')).toBeVisible({timeout:30000});
    const after=await page.locator('.review-player video').getAttribute('src');
    expect(after).not.toBe(before);
    await page.locator('.review-player video').evaluate((v:HTMLVideoElement)=>v.play());
    await expect.poll(()=>page.locator('.review-player video').evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeGreaterThan(.2);
    const id=await page.evaluate(()=>JSON.parse(localStorage.getItem('clappy-director-session')!).id as string);
    const doc=await (await page.request.get(`/api/sessions/${id}`)).json();
    const take=doc.takes.at(-1);const alternate=take.edits[1];
    const bella=alternate.segments.filter((s:{camera:string})=>s.camera==='b').reduce((n:number,s:{start:number;end:number})=>n+s.end-s.start,0);
    expect(bella/take.duration).toBeGreaterThanOrEqual(.75);
    const history=await (await page.request.get(`/api/sessions/${id}/events`)).json();
    const completed=history.find((e:{kind:string})=>e.kind==='agent.completed');
    expect(completed.payload.project).toBe('clappy-cinema-2026-0907');
    expect(completed.payload.mcp.some((e:{type:string;name:string})=>e.type==='mcp.response'&&e.name==='run_query')).toBe(true);
    // Both versions remain available after redirection.
    expect((await page.request.get(before!)).status()).toBe(200);
    await page.screenshot({path:'artifacts/studio-ai-edit.png',fullPage:true});
  }
  expect(errors).toEqual([]);
});

test('narrow iPhone-sized viewport has usable controls and no horizontal overflow',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Arm cameras'})).toBeEnabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({path:'artifacts/studio-mobile.png',fullPage:true});
});
