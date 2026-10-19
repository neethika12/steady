import { expect, test as setup } from '@playwright/test'

// Every browser test runs signed in to this test account (on the throwaway test stack only).
export const E2E_EMAIL = 'e2e@example.com'
export const E2E_PASSWORD = 'e2e test password 1'
export const STATE = 'e2e/.auth/state.json'

setup('sign in to the test account', async ({ page }) => {
  await page.goto('/')
  const signup = await page.request.post('/api/auth/signup', { data: { email: E2E_EMAIL, password: E2E_PASSWORD } })
  if (signup.status() === 409) {
    const login = await page.request.post('/api/auth/login', { data: { email: E2E_EMAIL, password: E2E_PASSWORD } })
    expect(login.ok(), await login.text()).toBeTruthy()
  } else {
    expect(signup.status(), await signup.text()).toBe(201)
  }
  await page.goto('/')
  await expect(page.getByRole('tab', { name: /To-Do/ })).toBeVisible()
  await page.context().storageState({ path: STATE })
})
