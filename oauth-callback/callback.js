"use strict";

const title = document.querySelector("#title");
const message = document.querySelector("#message");

function fail(text) {
  title.textContent = "无法完成授权";
  message.textContent = text;
}

try {
  const source = new URL(window.location.href);
  const state = source.searchParams.get("state") || "";
  const padded = state.replace(/-/g, "+").replace(/_/g, "/")
    + "=".repeat((4 - state.length % 4) % 4);
  const relay = JSON.parse(atob(padded));
  const port = Number(relay.port);
  const nonce = String(relay.nonce || "");

  if (
    relay.version !== 1
    || !Number.isInteger(port)
    || port < 49680
    || port > 49689
    || !/^[A-Za-z0-9_-]{20,200}$/.test(nonce)
  ) {
    throw new Error("invalid state");
  }

  const target = new URL(`http://127.0.0.1:${port}/oauth/callback`);
  for (const key of ["code", "state", "error", "error_description"]) {
    const value = source.searchParams.get(key);
    if (value) target.searchParams.set(key, value);
  }
  window.location.replace(target.toString());
} catch (_error) {
  fail("授权状态无效。请返回 AI 客户端，重新调用授权登录。");
}
