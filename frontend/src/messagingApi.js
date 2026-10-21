export async function api(path, options = {}) {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Could not reach the messaging service. Please try again."); }
  if (!response.ok) throw new Error(data.error || "The request could not be completed.");
  return data;
}

export const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
