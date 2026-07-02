const API_BASE_URL = "http://localhost:8080";

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/actuator/health`);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json();
}