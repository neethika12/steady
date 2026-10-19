import { expect, test, type Page } from '@playwright/test'

// Unique text per run, so tests don't depend on what earlier runs left behind.
const run = Date.now().toString(36)

async function api(page: Page, method: string, path: string, data?: unknown) {
  const r = await page.request.fetch(`/api${path}`, { method, data })
  expect(r.ok(), await r.text()).toBeTruthy()
  return r.json()
}

test('inbox: rapid capture keeps every task, then Move to date plans it @phone', async ({ page }) => {
  await page.goto('/#todo')
  await expect(page.getByRole('tab')).toHaveText([/To-Do/, /Calendar/, /Habit Tracker/, /Journal/, /Money/]) // no separate Inbox tab
  const inbox = page.getByRole('complementary', { name: 'Inbox' })
  const box = inbox.getByRole('textbox', { name: 'Capture a task' })
  for (const t of ['alpha', 'beta', 'gamma']) {
    await box.fill(`${t} ${run}`)
    await box.press('Enter')
  }
  for (const t of ['alpha', 'beta', 'gamma']) {
    await expect(inbox.getByText(`${t} ${run}`, { exact: true })).toBeVisible()
  }
  // Keyboard/mobile alternative to drag-and-drop.
  const item = inbox.getByRole('listitem').filter({ hasText: `alpha ${run}` })
  await item.getByRole('button', { name: 'Move to date' }).click()
  const dialog = page.getByRole('dialog', { name: `Plan “alpha ${run}”` })
  await dialog.getByRole('button', { name: /^Today/ }).click()
  await dialog.getByRole('button', { name: 'Plan', exact: true }).click()
  await expect(dialog).toBeHidden()
  await page.getByRole('button', { name: 'Today', exact: true }).click()
  await expect(page.getByLabel(/^Tasks for /).getByText(`alpha ${run}`, { exact: true })).toBeVisible()
  await expect(inbox.getByText(`alpha ${run}`, { exact: true })).toBeHidden()
})

test('to-do: the Inbox panel is always there and tasks can be dragged onto a day', async ({ page }) => {
  const title = `Drag me ${run}`
  await api(page, 'POST', '/tasks', { title })
  await page.goto('/#todo')
  await page.getByRole('radio', { name: 'Day' }).click()
  const inbox = page.getByRole('complementary', { name: 'Inbox' })
  await inbox.getByText(title, { exact: true }).dragTo(page.getByRole('region', { name: 'Day tasks' }))
  await expect(page.getByLabel(/^Tasks for /).getByRole('listitem').filter({ hasText: title })).toBeVisible()
  await expect(inbox.getByText(title, { exact: true })).toBeHidden() // it has a day now
  await page.getByRole('radio', { name: 'Week' }).click()
  await expect(inbox).toBeVisible()
  await expect(inbox.getByRole('button', { name: 'Hide' })).toHaveCount(0) // permanent

  // Its own full-height column, flush against the left edge, on every tab.
  const viewport = page.viewportSize()!
  const box = (await inbox.boundingBox())!
  expect(Math.round(box.x)).toBe(0)
  expect(Math.round(box.height)).toBe(viewport.height)
  // Date controls sit beside Day/Week, and in Week view the arrows move a whole week.
  const picker = page.getByLabel('Pick a date')
  const before = await picker.inputValue()
  await page.getByRole('button', { name: 'Next week' }).click()
  const after = await picker.inputValue()
  expect((Date.parse(after) - Date.parse(before)) / 86_400_000).toBe(7)
  await page.getByRole('button', { name: 'Today', exact: true }).click()
  await page.getByRole('tab', { name: 'Habit Tracker' }).click()
  await expect(inbox).toBeVisible()
})

/** Helpers for the Day view: tasks are list items (Anytime list or timeline blocks); details open in a panel. */
const dayTask = (page: Page, title: string) => page.getByLabel(/^Tasks for /).getByRole('listitem').filter({ hasText: title }).first()
const panel = (page: Page, title: string) => page.getByRole('dialog', { name: title })
async function openDay(page: Page, isoDate?: string) {
  await page.goto('/#todo')
  await page.getByRole('radio', { name: 'Day' }).click()
  if (isoDate) await page.getByLabel('Pick a date').fill(isoDate)
  else await page.getByRole('button', { name: 'Today', exact: true }).click()
}
async function openCalendar(page: Page, isoDate: string) {
  await page.goto('/#calendar')
  await page.getByLabel('Pick a date').fill(isoDate)
}
async function quietDay(page: Page, offset: number) {
  const settings = await api(page, 'GET', '/settings')
  const d = new Date(`${settings.today}T00:00:00Z`)
  // A different far-future day on every run (about 100 years of room), so runs never share a day.
  d.setUTCDate(d.getUTCDate() + offset + Math.floor(Math.random() * 36500))
  return d.toISOString().slice(0, 10)
}

test('to-do: not completed needs a reason, and the earlier day keeps its record', async ({ page }) => {
  const settings = await api(page, 'GET', '/settings')
  const yesterday = new Date(`${settings.today}T00:00:00Z`)
  yesterday.setUTCDate(yesterday.getUTCDate() - 1)
  const title = `Update resume ${run}`
  await api(page, 'POST', '/tasks', { title, planned_date: yesterday.toISOString().slice(0, 10), planned_time: '09:00' })

  await openDay(page)
  await page.getByRole('button', { name: 'Yesterday', exact: true }).click()
  const block = dayTask(page, title)
  await expect(block.getByText('9:00 AM')).toBeVisible() // shown on the timeline at its time
  await block.getByRole('button', { name: `Mark not completed: ${title}` }).click()
  const sheet = panel(page, title)
  await sheet.getByRole('button', { name: 'Save as not completed' }).click()
  await expect(sheet.getByText('Please write a short reason')).toBeVisible() // a reason is required
  await sheet.getByRole('textbox').fill('Meetings ran over')
  await sheet.getByText('Not enough time', { exact: true }).click()
  await sheet.getByRole('button', { name: 'Save as not completed' }).click()
  await expect(sheet.getByText('✗ Not completed')).toBeVisible()
  await expect(sheet.getByText('Meetings ran over')).toBeVisible()
  // Created directly on a day: it stays there and you're asked what to do (not dumped in the Inbox).
  await expect(sheet.getByText('What should happen to it?')).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Inbox' }).getByText(title)).toHaveCount(0)
  await sheet.getByRole('button', { name: 'Move to today' }).click()
  await page.keyboard.press('Escape')

  // Today shows it carried forward (same time); completing it doesn't change yesterday.
  await page.getByRole('button', { name: 'Today', exact: true }).click()
  await expect(dayTask(page, title).getByText('9:00 AM')).toBeVisible()
  await dayTask(page, title).getByRole('button', { name: `Open ${title}` }).click()
  await expect(panel(page, title).getByText(/Carried from/)).toBeVisible()
  await page.keyboard.press('Escape')
  await dayTask(page, title).getByRole('button', { name: `Mark completed: ${title}` }).click()
  await expect(dayTask(page, title).getByRole('button', { name: `Undo completion: ${title}` })).toBeVisible()
  await page.getByRole('button', { name: 'Yesterday', exact: true }).click()
  await expect(dayTask(page, title).getByRole('button', { name: `Not completed: ${title}` })).toBeVisible()
})

test('to-do: unfinished Inbox tasks go back to the Inbox; day tasks can be moved there or left', async ({ page }) => {
  const settings = await api(page, 'GET', '/settings')
  const fromInbox = `Captured ${run}`
  const onDay = `Made today ${run}`
  const a = await api(page, 'POST', '/tasks', { title: fromInbox })
  await api(page, 'PUT', `/tasks/${a.id}/schedule`, { planned_date: settings.today }) // like dragging it onto today
  await api(page, 'POST', '/tasks', { title: onDay, planned_date: settings.today })
  await openDay(page)
  const inbox = page.getByRole('complementary', { name: 'Inbox' })

  for (const title of [fromInbox, onDay]) {
    await dayTask(page, title).getByRole('button', { name: `Mark not completed: ${title}` }).click()
    const sheet = panel(page, title)
    await sheet.getByRole('textbox').fill('Ran out of time')
    await sheet.getByRole('button', { name: 'Save as not completed' }).click()
    await expect(sheet.getByText('✗ Not completed')).toBeVisible()
    if (title === onDay) {
      await sheet.getByRole('button', { name: 'Leave it here' }).click()
      await expect(sheet.getByText('Left on this day.')).toBeVisible()
    }
    await page.keyboard.press('Escape')
  }
  await expect(inbox.getByText(fromInbox)).toBeVisible() // came from the Inbox: back automatically
  await expect(inbox.getByText(onDay)).toHaveCount(0) // made on the day and left there
  await dayTask(page, onDay).getByRole('button', { name: `Open ${onDay}` }).click()
  await panel(page, onDay).getByRole('button', { name: 'Move to Inbox' }).click() // changed your mind
  await expect(inbox.getByText(onDay)).toBeVisible()
})

test('to-do: a task can be planned for a time range', async ({ page }) => {
  const title = `Deep work ${run}`
  await openDay(page)
  await page.getByRole('button', { name: '+ New task' }).click()
  const form = page.getByRole('dialog', { name: 'New task' })
  await form.getByLabel('Title').fill(title)
  await form.getByRole('radio', { name: 'From – to' }).click()
  await form.getByLabel('Start time').fill('10:30')
  await form.getByLabel('End time').fill('09:00')
  await expect(form.getByText('The end time must be after the start time.')).toBeVisible()
  await expect(form.getByRole('button', { name: 'Add task' })).toBeDisabled()
  await form.getByLabel('Start time').fill('09:00')
  await form.getByLabel('End time').fill('10:30')
  await form.getByRole('button', { name: 'Add task' }).click()
  await expect(dayTask(page, title).getByText('9:00 AM – 10:30 AM')).toBeVisible()
})

test('to-do: a time can be added later by editing an Anytime task', async ({ page }) => {
  const settings = await api(page, 'GET', '/settings')
  const title = `Add a time later ${run}`
  await api(page, 'POST', '/tasks', { title, planned_date: settings.today }) // created as Anytime
  await openDay(page)
  await expect(page.getByRole('region', { name: 'Timeline' })).toHaveCount(0) // the timeline lives in the Calendar tab
  await expect(dayTask(page, title).getByText('Anytime')).toBeVisible()
  await dayTask(page, title).getByRole('button', { name: `Open ${title}` }).click()
  await panel(page, title).getByRole('button', { name: 'Edit' }).click()
  const form = page.getByRole('dialog', { name: 'Edit task' })
  await form.getByRole('radio', { name: 'From – to' }).click()
  await form.getByLabel('Start time').fill('16:00')
  await form.getByLabel('End time').fill('17:15')
  await form.getByRole('button', { name: 'Save' }).click()
  await expect(form).toBeHidden()
  await page.keyboard.press('Escape')
  await expect(dayTask(page, title).getByText('4:00 PM – 5:15 PM')).toBeVisible()
  // Editing again shows the saved range, and Anytime clears it.
  await dayTask(page, title).getByRole('button', { name: `Open ${title}` }).click()
  await panel(page, title).getByRole('button', { name: 'Edit' }).click()
  await expect(form.getByLabel('Start time')).toHaveValue('16:00')
  await form.getByRole('radio', { name: 'Anytime' }).click()
  await form.getByRole('button', { name: 'Save' }).click()
  await page.keyboard.press('Escape')
  await expect(dayTask(page, title).getByText('Anytime')).toBeVisible()
})

test('calendar: shows only timed tasks; Inbox tasks can be dropped on a time and blocks moved', async ({ page }) => {
  // A tall window keeps the afternoon slots on screen (simulated drags can't auto-scroll like a real browser).
  await page.setViewportSize({ width: 1280, height: 1800 })
  const day = await quietDay(page, 400)
  const anytimeTitle = `No time set ${run}`
  const title = `Find a slot ${run}`
  await api(page, 'POST', '/tasks', { title: anytimeTitle, planned_date: day })
  await api(page, 'POST', '/tasks', { title }) // in the Inbox, no estimate
  await openCalendar(page, day)
  const timeline = page.getByRole('region', { name: 'Timeline' })
  await expect(page.getByRole('region', { name: 'Anytime tasks' })).toHaveCount(0)
  await expect(page.getByText(anytimeTitle)).toHaveCount(0) // anytime tasks stay in To-Do

  const inbox = page.getByRole('complementary', { name: 'Inbox' })
  await inbox.getByRole('listitem').filter({ hasText: title }).dragTo(timeline.getByLabel('Time slot 9:00 AM'))
  const block = timeline.getByRole('listitem').filter({ hasText: title })
  await expect(block.getByText('9:00 AM – 10:00 AM')).toBeVisible() // no estimate: one hour

  // Moving it within the timeline keeps its length.
  await block.dragTo(timeline.getByLabel('Time slot 2:30 PM'))
  await expect(block.getByText('2:30 PM – 3:30 PM')).toBeVisible()

  // To-Do lists both: the timed one with its time, the anytime one too.
  await page.getByRole('tab', { name: 'To-Do' }).click()
  await page.getByRole('radio', { name: 'Day' }).click()
  await expect(dayTask(page, title).getByText('2:30 PM – 3:30 PM')).toBeVisible()
  await expect(dayTask(page, anytimeTitle).getByText('Anytime')).toBeVisible()
})

test('calendar: click or drag on the timeline to create a task at that time', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1800 })
  const day = await quietDay(page, 800)
  await openCalendar(page, day)
  const timeline = page.getByRole('region', { name: 'Timeline' })

  // A single click: one hour from that spot.
  await timeline.getByRole('button', { name: 'New task at 3:00 PM' }).click()
  let form = page.getByRole('dialog', { name: 'New task' })
  await expect(form.getByLabel('Start time')).toHaveValue('15:00')
  await expect(form.getByLabel('End time')).toHaveValue('16:00')
  await form.getByLabel('Title').fill(`Clicked ${run}`)
  await form.getByRole('button', { name: 'Add task' }).click()
  await expect(timeline.getByRole('listitem').filter({ hasText: `Clicked ${run}` }).getByText('3:00 PM – 4:00 PM')).toBeVisible()

  // Click and drag from 1:00 PM down to the 2:00 PM spot: 1:00–2:30 PM.
  const from = (await timeline.getByRole('button', { name: 'New task at 1:00 PM' }).boundingBox())!
  const to = (await timeline.getByRole('button', { name: 'New task at 2:00 PM' }).boundingBox())!
  await page.mouse.move(from.x + 40, from.y + 8)
  await page.mouse.down()
  await page.mouse.move(to.x + 40, to.y + 8, { steps: 6 })
  await expect(timeline.getByText('1:00 PM – 2:30 PM')).toBeVisible() // live preview of the selection
  await page.mouse.up()
  form = page.getByRole('dialog', { name: 'New task' })
  await expect(form.getByLabel('Start time')).toHaveValue('13:00')
  await expect(form.getByLabel('End time')).toHaveValue('14:30')
  await form.getByLabel('Title').fill(`Dragged ${run}`)
  await form.getByRole('button', { name: 'Add task' }).click()
  await expect(timeline.getByRole('listitem').filter({ hasText: `Dragged ${run}` }).getByText('1:00 PM – 2:30 PM')).toBeVisible()

  // Keyboard: focus a spot and press Enter.
  await timeline.getByRole('button', { name: 'New task at 7:30 AM' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog', { name: 'New task' }).getByLabel('Start time')).toHaveValue('07:30')
})

test('calendar: night owls can set their timeline hours past midnight', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 2400 })
  const day = await quietDay(page, 1100)
  try {
    await openCalendar(page, day)
    const timeline = page.getByRole('region', { name: 'Timeline' })
    await timeline.getByRole('button', { name: 'Change timeline hours' }).click()
    const dialog = page.getByRole('dialog', { name: 'Timeline hours' })
    await dialog.getByRole('button', { name: /Night owl/ }).click()
    await expect(dialog.getByText('Your day runs past midnight.')).toBeVisible()
    await dialog.getByRole('button', { name: 'Save hours' }).click()
    await expect(dialog).toBeHidden()

    // The timeline now starts at 11 AM and continues past midnight to 2 AM.
    await expect(timeline.getByText('11:00 AM – 2:00 AM')).toBeVisible()
    await expect(timeline.getByRole('button', { name: 'New task at 10:30 AM' })).toHaveCount(0)
    await expect(timeline.getByText('Midnight')).toBeVisible()
    await expect(timeline.getByRole('button', { name: 'New task at 1:30 AM' })).toBeVisible() // last half-hour
    await timeline.getByRole('button', { name: 'New task at 11:30 PM' }).click()
    const form = page.getByRole('dialog', { name: 'New task' })
    await expect(form.getByLabel('Start time')).toHaveValue('23:30')
    await expect(form.getByLabel('End time')).toHaveValue('00:30') // runs past midnight
    await expect(form.getByText('Runs past midnight')).toBeVisible()
    await form.getByLabel('Title').fill(`Late session ${run}`)
    await form.getByRole('button', { name: 'Add task' }).click()
    await expect(timeline.getByRole('listitem').filter({ hasText: `Late session ${run}` }).getByText('11:30 PM – 12:30 AM')).toBeVisible()
  } finally {
    await api(page, 'PUT', '/settings', { timeline_start: '07:00', timeline_end: '22:00' }) // other tests expect the default
  }
})

test('to-do: tasks are split into High / Medium / Low columns, and dragging changes priority', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1400 }) // keep the columns on screen for the simulated drag
  const day = await quietDay(page, 1300)
  for (const [title, priority] of [['Low one', 'low'], ['High one', 'high'], ['Medium one', 'medium'], ['High timed', 'high']] as const) {
    await api(page, 'POST', '/tasks', { title: `${title} ${run}`, priority, planned_date: day, ...(title === 'High timed' ? { planned_time: '09:00' } : {}) })
  }
  await openDay(page, day)
  const groups = page.getByRole('region', { name: 'Day tasks' }).getByRole('region')
  await expect(groups).toHaveCount(3)
  await expect(groups.nth(0)).toHaveAccessibleName('High priority')
  await expect(groups.nth(1)).toHaveAccessibleName('Medium priority')
  await expect(groups.nth(2)).toHaveAccessibleName('Low priority')
  // Within a group, timed tasks come first.
  await expect(groups.nth(0).getByRole('listitem')).toHaveText([new RegExp(`High timed ${run}`), new RegExp(`High one ${run}`)])
  await expect(groups.nth(2).getByText(`Low one ${run}`)).toBeVisible()

  // Drag a task into another column to change its priority.
  await groups.nth(2).getByRole('listitem').filter({ hasText: `Low one ${run}` }).dragTo(groups.nth(0))
  await expect(groups.nth(0).getByText(`Low one ${run}`)).toBeVisible()
  await expect(groups.nth(2).getByText(`Low one ${run}`)).toHaveCount(0)
  const moved = (await api(page, 'GET', `/plans/day?date=${day}`)).plans.find((p: { task: { title: string } }) => p.task.title === `Low one ${run}`)
  expect(moved.task.priority).toBe('high')
})

test('to-do: click a priority column to add a task there; no pop-up after adding or completing', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1400 })
  const title = `From the low column ${run}`
  await openDay(page)
  const low = page.getByRole('region', { name: 'Day tasks' }).getByRole('region', { name: 'Low priority' })
  await low.getByRole('button', { name: 'Add low priority task' }).click()
  const form = page.getByRole('dialog', { name: 'New task' })
  await expect(form.getByRole('radio', { name: 'Low' })).toHaveAttribute('aria-checked', 'true')
  await form.getByLabel('Title').fill(title)
  await form.getByRole('button', { name: 'Add task' }).click()
  await expect(low.getByText(title)).toBeVisible()
  await expect(page.getByText('Task added')).toHaveCount(0)

  // Clicking the empty part of a column also opens the form with that priority.
  const high = page.getByRole('region', { name: 'Day tasks' }).getByRole('region', { name: 'High priority' })
  await high.getByRole('heading', { name: /High/ }).click() // free space in the column (not a task card)
  await expect(page.getByRole('dialog', { name: 'New task' }).getByRole('radio', { name: 'High' })).toHaveAttribute('aria-checked', 'true')
  await page.keyboard.press('Escape')

  // Completing: the card animates; no "Task completed" notification.
  await low.getByRole('button', { name: `Done: ${title}` }).click()
  await expect(low.getByRole('button', { name: `Undo completion: ${title}` })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: /completed|Done\./ })).toHaveCount(0)
})

test('to-do: a cancelled task only offers Restore, which puts it back on the same day', async ({ page }) => {
  const settings = await api(page, 'GET', '/settings')
  const title = `Drop me ${run}`
  const t = await api(page, 'POST', '/tasks', { title, planned_date: settings.today })
  await api(page, 'POST', `/tasks/${t.id}/cancel`)
  await openDay(page)
  await page.getByText(/^Cancelled · \d+$/).click() // cancelled tasks are tucked away in their own section
  const row = dayTask(page, title)
  await expect(row.getByText('Cancelled · not counted')).toBeVisible()
  await expect(row.getByRole('button', { name: /Completed|Cancel task/ })).toHaveCount(0)
  await row.getByRole('button', { name: `More actions for ${title}` }).click()
  await expect(row.getByRole('button', { name: 'Cancel task' })).toHaveCount(0)
  await row.getByRole('button', { name: 'Restore' }).click()
  // Back on today, ready to mark, and not in the Inbox.
  await expect(dayTask(page, title).getByRole('button', { name: `Mark completed: ${title}` })).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Inbox' }).getByText(title)).toHaveCount(0)
})

test('to-do: delete asks first, then removes the task everywhere', async ({ page }) => {
  const settings = await api(page, 'GET', '/settings')
  const onDay = `Delete from day ${run}`
  const inInbox = `Delete from inbox ${run}`
  await api(page, 'POST', '/tasks', { title: onDay, planned_date: settings.today })
  await api(page, 'POST', '/tasks', { title: inInbox })
  await openDay(page)

  await dayTask(page, onDay).getByRole('button', { name: `More actions for ${onDay}` }).click()
  const sheet = panel(page, onDay)
  await sheet.getByRole('button', { name: 'Delete task' }).click()
  const confirm = page.getByRole('dialog', { name: 'Delete this task?' })
  await confirm.getByRole('button', { name: 'Keep it' }).click() // changing your mind keeps it
  await expect(sheet).toBeVisible()
  await sheet.getByRole('button', { name: `More actions for ${onDay}` }).click() // the menu closed when the dialog opened
  await sheet.getByRole('button', { name: 'Delete task' }).click()
  await confirm.getByRole('button', { name: 'Delete permanently' }).click()
  await expect(dayTask(page, onDay)).toHaveCount(0)

  const inbox = page.getByRole('complementary', { name: 'Inbox' })
  const item = inbox.getByRole('listitem').filter({ hasText: inInbox })
  await item.getByRole('button', { name: `More actions for ${inInbox}` }).click()
  await item.getByRole('button', { name: 'Delete task' }).click()
  await page.getByRole('dialog', { name: 'Delete this task?' }).getByRole('button', { name: 'Delete permanently' }).click()
  await expect(item).toHaveCount(0)
  expect((await api(page, 'GET', '/tasks?view=unscheduled')).some((t: { title: string }) => t.title === inInbox)).toBe(false)
})

test('habits: create a daily habit and check in @phone', async ({ page }) => {
  const name = `Stretch ${run}`
  await page.goto('/#habits')
  await page.getByRole('button', { name: '+ New habit' }).click()
  const dialog = page.getByRole('dialog', { name: 'New habit' })
  await dialog.getByLabel('Name').fill(name)
  await dialog.getByRole('button', { name: 'Create habit' }).click()
  await expect(dialog).toBeHidden()
  const row = page.getByRole('listitem').filter({ hasText: name })
  await row.getByRole('button', { name: `${name}: mark done` }).click()
  await expect(row.getByText('1 day streak')).toBeVisible()
  await expect(row.getByRole('button', { name: `${name}: done, press to undo` })).toHaveAttribute('aria-pressed', 'true')
})

test('journal: autosaves, survives reload, and asks before overwriting a newer save', async ({ page }) => {
  const settings = await api(page, 'GET', '/settings')
  // Use a quiet past date so reruns don't collide with each other.
  const day = new Date(`${settings.today}T00:00:00Z`)
  day.setUTCDate(day.getUTCDate() - 400 - (Date.now() % 300))
  const d = day.toISOString().slice(0, 10)

  await page.goto('/#journal')
  await page.getByLabel('Pick a date').fill(d)
  const body = page.getByLabel('Free writing')
  await body.fill(`First words ${run}`)
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Free writing')).toHaveValue(`First words ${run}`)

  // Another device saves a newer version...
  const current = await api(page, 'GET', `/journal/${d}`)
  await api(page, 'PUT', `/journal/${d}`, { ...current, body: `From the phone ${run}`, base_version: current.version })
  // ...then this screen keeps typing on top of the old version.
  await page.getByLabel('Free writing').fill(`First words, edited ${run}`)
  const alert = page.getByRole('alert').filter({ hasText: 'changed somewhere else' })
  await expect(alert).toBeVisible()
  expect((await api(page, 'GET', `/journal/${d}`)).body).toBe(`From the phone ${run}`) // not overwritten
  await alert.getByRole('button', { name: 'Keep my version' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible()
  expect((await api(page, 'GET', `/journal/${d}`)).body).toBe(`First words, edited ${run}`)
})

test('money: set up accounts, then spending lowers debit and raises what the card owes', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1400 })
  await page.goto('/#money')
  const first = await api(page, 'GET', '/finance/overview')
  if (!first.set_up) {
    // First-time setup: how many accounts, then each one's balance.
    await expect(page.getByText('How many debit accounts do you have?')).toBeVisible()
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByLabel('Name').first().fill('Everyday debit')
    await page.getByLabel('Current balance').fill('1,200.50')
    await page.getByLabel('Name').nth(1).fill('Rewards card')
    await expect(page.getByLabel('Amount owed now')).toHaveValue('0') // a card starts at 0 owed unless you say otherwise
    await page.getByRole('button', { name: 'Start tracking' }).click()
  }
  await expect(page.getByRole('region', { name: 'Accounts', exact: true })).toBeVisible() // set up and loaded
  const before = await api(page, 'GET', '/finance/overview')
  const debit = before.accounts.find((a: { type: string }) => a.type === 'debit')
  const credit = before.accounts.find((a: { type: string }) => a.type === 'credit')
  await page.getByRole('button', { name: 'Today', exact: true }).click()

  const form = page.getByRole('region', { name: 'Add money entry' })
  await form.getByLabel('Amount').fill('42.75')
  await form.getByText('Groceries', { exact: true }).click()
  await form.getByLabel(/Why/).fill(`Weekly shop ${run}`)
  await form.getByRole('radio', { name: new RegExp(debit.name) }).click()
  await form.getByRole('button', { name: 'Add spending' }).click()
  await expect(page.getByRole('region', { name: 'Day entries' }).getByText(`Weekly shop ${run}`)).toBeVisible()

  await form.getByLabel('Amount').fill('15')
  await form.getByText('Dining out', { exact: true }).click()
  await form.getByRole('radio', { name: new RegExp(credit.name) }).click()
  await form.getByRole('button', { name: 'Add spending' }).click()
  await expect(form.getByLabel('Amount')).toHaveValue('') // cleared, ready for the next one

  await expect.poll(async () => {
    const after = await api(page, 'GET', '/finance/overview')
    const bal = (id: string) => after.accounts.find((a: { id: string }) => a.id === id).balance_cents
    return [debit.balance_cents - bal(debit.id), bal(credit.id) - credit.balance_cents]
  }).toEqual([4275, 1500]) // debit down by 42.75, card owed up by 15.00
})

test('money: a monthly bill is added on its day, shows as scheduled ahead, and stopping keeps what it added', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1600 })
  if (!(await api(page, 'GET', '/finance/overview')).set_up) {
    await api(page, 'POST', '/finance/setup', { accounts: [
      { name: 'Everyday debit', type: 'debit', balance_cents: 100000 }, { name: 'Rewards card', type: 'credit', balance_cents: 0 }] })
  }
  const before = await api(page, 'GET', '/finance/overview')
  const credit = before.accounts.find((a: { type: string; archived: boolean }) => a.type === 'credit' && !a.archived)
  const name = `Phone bill ${run}`
  await page.goto('/#money')
  await page.getByRole('button', { name: 'Today', exact: true }).click()

  const repeating = page.getByRole('region', { name: 'Repeating' })
  await repeating.getByRole('button', { name: '+ Add repeating' }).click()
  const dialog = panel(page, 'Add a repeating entry')
  await dialog.getByLabel('Name').fill(name)
  await dialog.getByLabel('Amount').fill('30')
  await dialog.getByText('Bills & utilities', { exact: true }).click()
  await dialog.getByRole('radio', { name: new RegExp(credit.name) }).click()
  await expect(dialog.getByLabel('Repeats')).toHaveValue('monthly-1') // monthly by default, starting today
  await dialog.getByRole('button', { name: 'Add repeating' }).click()
  await expect(dialog).toBeHidden()

  // Today's one is recorded straight away, tagged as repeating, and the card owes 30 more.
  const row = repeating.getByRole('listitem').filter({ hasText: name })
  await expect(row).toContainText(/Monthly on the \d+/)
  await expect(row).toContainText('Next ')
  const entry = page.getByRole('region', { name: 'Day entries' }).getByRole('listitem').filter({ hasText: name })
  await expect(entry).toContainText('Repeats')
  await expect.poll(async () => {
    const o = await api(page, 'GET', '/finance/overview')
    return o.accounts.find((a: { id: string }) => a.id === credit.id).balance_cents - credit.balance_cents
  }).toBe(3000)

  // Next month's date shows it as scheduled, not yet recorded.
  const rule = (await api(page, 'GET', '/finance/recurring')).rules.find((r: { name: string }) => r.name === name)
  await page.getByLabel('Pick a date').fill(rule.next_on)
  await expect(page.getByLabel('Scheduled')).toContainText(name)

  // Stopping it keeps the entry it already added.
  await page.getByRole('button', { name: 'Today', exact: true }).click()
  await row.getByRole('button', { name: `Stop ${name}` }).click()
  await panel(page, `Stop “${name}”?`).getByRole('button', { name: 'Stop repeating' }).click()
  await expect(row).toHaveCount(0)
  await expect(entry).toBeVisible()
})

test('money: Splitwise totals are entered by hand and count towards net', async ({ page }) => {
  if (!(await api(page, 'GET', '/finance/overview')).set_up) {
    await api(page, 'POST', '/finance/setup', { accounts: [
      { name: 'Everyday debit', type: 'debit', balance_cents: 100000 }, { name: 'Rewards card', type: 'credit', balance_cents: 0 }] })
  }
  const get = 1000 + Math.floor(Math.random() * 9000)
  await page.goto('/#money')
  const sw = page.getByRole('group', { name: 'Splitwise' })
  await sw.getByRole('button', { name: 'Update' }).click()
  const dialog = panel(page, 'Update Splitwise')
  await dialog.getByLabel('You should get').fill((get / 100).toFixed(2))
  await dialog.getByLabel('You should pay').fill('15')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()
  await expect(sw).toContainText(`$${(get / 100).toFixed(2)}`)
  await expect(sw).toContainText('$15.00')
  const o = await api(page, 'GET', '/finance/overview')
  expect(o.net_cents).toBe(o.available_cents - o.owed_cents + get - 1500)
})

test('money insights: calculated trends, and saving tips from the local AI when it is running', async ({ page }) => {
  test.setTimeout(150_000)
  await page.setViewportSize({ width: 1280, height: 1600 })
  const t = await api(page, 'GET', '/finance/trends')
  test.skip(t.expense_entries < 3, 'Needs a few money entries (the earlier money tests add them)')
  await page.goto('/#money')
  const card = page.getByRole('region', { name: 'Money insights' })
  await expect(card.getByRole('table', { name: 'Spending by category over time' })).toBeVisible()
  await expect(card).toContainText('So far this month')
  const status = await api(page, 'GET', '/ai/status')
  if (!status.available) return
  await card.getByRole('button', { name: 'Get saving tips with local AI' }).click()
  const tips = card.getByLabel('AI saving tips')
  await expect(tips.getByText('Where to cut back').or(tips.getByRole('alert'))).toBeVisible({ timeout: 120_000 })
  if (await tips.getByText('Where to cut back').isVisible()) {
    await expect(tips).toContainText('save about')
    await expect(tips).toContainText('Savings are calculated by the app')
  }
})

test('local AI: daily plan is a proposal until accepted', async ({ page }) => {
  const status = await api(page, 'GET', '/ai/status')
  test.skip(!status.available, 'Local AI (Ollama + model) is not running')
  test.setTimeout(120_000)
  const settings = await api(page, 'GET', '/settings')
  const d = new Date(`${settings.today}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + 30 + (Date.now() % 200))
  const day = d.toISOString().slice(0, 10)
  const title = `Quick call ${run}`
  await api(page, 'POST', '/tasks', { title, estimated_minutes: 10, priority: 'high' })

  await page.goto('/#todo')
  await page.getByLabel('Pick a date').fill(day)
  await page.getByRole('button', { name: 'Suggest a plan (AI)' }).click()
  const dialog = page.getByRole('dialog', { name: /Suggest a plan/ })
  const mine = dialog.locator('label', { hasText: title }).getByRole('checkbox')
  await expect(mine).toBeVisible() // candidate list loaded
  await dialog.getByRole('button', { name: 'Select none' }).click()
  await mine.check()
  await expect(dialog.getByText('Tasks to consider (1 selected)')).toBeVisible()
  await dialog.getByRole('button', { name: 'Suggest a plan' }).click()
  await expect(dialog.getByText('Suggestion from local AI')).toBeVisible({ timeout: 90_000 })
  const before = (await api(page, 'GET', `/plans/day?date=${day}`)).plans as { task: { title: string } }[]
  expect(before.some((p) => p.task.title === title)).toBe(false) // nothing saved yet
  await dialog.getByRole('button', { name: /^Plan 1 task/ }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText(title, { exact: true })).toBeVisible()
})


test.describe('accounts', () => {
  test.use({ storageState: { cookies: [], origins: [] } }) // start signed out

  test('each person sees only their own tasks; log out and back in', async ({ page }) => {
    const a = `a-${run}@example.com`, b = `b-${run}@example.com`, pw = 'a long test password'
    const secret = `Secret plan ${run}`
    const signUp = async (email: string) => {
      await page.goto('/')
      await page.getByRole('radio', { name: 'Create account' }).click()
      await page.getByLabel('Email').fill(email)
      await page.getByLabel('Password').fill(pw)
      await page.getByRole('button', { name: 'Create account' }).click()
      await expect(page.getByRole('tab', { name: /To-Do/ })).toBeVisible()
    }
    const logOut = async () => {
      await page.getByRole('button', { name: 'Account' }).click()
      await page.getByRole('menuitem', { name: 'Log out' }).click()
      await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible()
    }
    await signUp(a)
    await page.getByLabel('Capture a task').fill(secret)
    await page.getByLabel('Capture a task').press('Enter')
    await expect(page.getByText(secret)).toBeVisible()
    await logOut()

    await signUp(b)
    await expect(page.getByText(secret)).toHaveCount(0) // someone else's task is invisible
    expect(JSON.stringify(await (await page.request.get('/api/tasks?status=all')).json())).not.toContain(secret)
    await logOut()

    await page.getByLabel('Email').fill(a)
    await page.getByLabel('Password').fill('wrong password here')
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('alert')).toContainText("don't match")
    await page.getByLabel('Password').fill(pw)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByText(secret)).toBeVisible()
  })
})
