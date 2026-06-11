import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage();
const logs = [];
const errors = [];
page.on("console", (msg) => logs.push(`${msg.type()}: ${msg.text()}`));
page.on("pageerror", (err) => errors.push(String(err)));

const resp = await page.goto("http://127.0.0.1:8080/", { waitUntil: "networkidle" });
console.log("status", resp?.status());
console.log("title", await page.title());
const rootHtml = await page.locator("#root").innerHTML();
console.log("root innerHTML length", rootHtml.length);
console.log("root preview", rootHtml.slice(0, 400));
const bodyText = await page.locator("body").innerText();
console.log("body text", JSON.stringify(bodyText.slice(0, 300)));
console.log("page errors", errors);
console.log("console", logs);
await browser.close();
