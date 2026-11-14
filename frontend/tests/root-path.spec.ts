import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const rootPath = (process.env.ROOT_PATH ?? "").replace(/\/+$/, "")

async function registerStrippingProxy(page: Page) {
  await page.route("**/*", async (route) => {
    const publicUrl = new URL(route.request().url())
    if (!publicUrl.pathname.startsWith(`${rootPath}/`)) {
      await route.continue()
      return
    }

    publicUrl.pathname = publicUrl.pathname.slice(rootPath.length) || "/"
    const response = await route.fetch({ url: publicUrl.href })
    await route.fulfill({
      body: await response.body(),
      contentType: response.headers()["content-type"],
      status: response.status(),
    })
  })
}

test("production frontend works below the configured root path", async ({
  page,
}) => {
  test.skip(!rootPath, "Set ROOT_PATH to exercise the prefixed deployment")

  const assetUrls: string[] = []
  const apiUrls: string[] = []
  await registerStrippingProxy(page)

  page.on("request", (request) => {
    const url = new URL(request.url())
    if (url.pathname.includes("/assets/")) {
      assetUrls.push(url.pathname)
    }
  })

  await page.route(/\/api\/v1\//, async (route) => {
    const url = new URL(route.request().url())
    apiUrls.push(url.pathname)

    if (url.pathname.endsWith("/users/me")) {
      await route.fulfill({
        json: {
          email: "prefix-test@example.com",
          full_name: "Prefix Test",
          id: "00000000-0000-0000-0000-000000000001",
          is_active: true,
          is_superuser: false,
        },
      })
      return
    }

    if (url.pathname.endsWith("/items/")) {
      await route.fulfill({ json: { count: 0, data: [] } })
      return
    }

    await route.continue()
  })

  await page.addInitScript(() => {
    if (!sessionStorage.getItem("root-path-test-auth-seeded")) {
      localStorage.setItem("access_token", "prefix-test-token")
      sessionStorage.setItem("root-path-test-auth-seeded", "true")
    }
  })
  await page.goto(`${rootPath}/items`)
  await expect(
    page.getByRole("heading", { name: "Items", exact: true }),
  ).toBeVisible()

  expect(assetUrls.some((url) => url.startsWith(`${rootPath}/assets/`))).toBe(
    true,
  )
  expect(apiUrls).toContain(`${rootPath}/api/v1/users/me`)
  expect(apiUrls).toContain(`${rootPath}/api/v1/items/`)

  await page.getByRole("link", { name: "Dashboard" }).click()
  await expect(
    page.getByText("Welcome back, nice to see you again!"),
  ).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`${rootPath}/$`))

  await page.getByRole("link", { name: "Items" }).click()
  await expect(
    page.getByRole("heading", { name: "Items", exact: true }),
  ).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`${rootPath}/items$`))

  await page.reload()
  await expect(
    page.getByRole("heading", { name: "Items", exact: true }),
  ).toBeVisible()
})

test("authentication errors redirect below the configured root path", async ({
  page,
}) => {
  test.skip(!rootPath, "Set ROOT_PATH to exercise the prefixed deployment")

  await registerStrippingProxy(page)
  await page.route(/\/api\/v1\/users\/me$/, async (route) => {
    await route.fulfill({ json: { detail: "Not authenticated" }, status: 401 })
  })
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("root-path-test-auth-seeded")) {
      localStorage.setItem("access_token", "invalid-prefix-test-token")
      sessionStorage.setItem("root-path-test-auth-seeded", "true")
    }
  })

  await page.goto(`${rootPath}/items`)

  await expect(page).toHaveURL(new RegExp(`${rootPath}/login$`), {
    timeout: 15_000,
  })
  await expect(
    page.getByRole("heading", { name: "Login to your account" }),
  ).toBeVisible()
})
