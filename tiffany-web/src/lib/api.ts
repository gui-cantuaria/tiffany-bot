export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  status?: number;
}

export async function getGuildConfig(guildId: string): Promise<ApiResponse<any>> {
  try {
    const res = await fetch(`/api/guilds/${guildId}/config`, {
      cache: "no-store",
    });
    
    if (!res.ok) {
      let errorMsg = "Failed to fetch configuration";
      try {
        const errorData = await res.json();
        errorMsg = errorData.error || errorMsg;
      } catch (e) {}
      return { success: false, error: errorMsg, status: res.status };
    }
    
    const data = await res.json();
    return { success: true, data: data.config };
  } catch (error) {
    return { success: false, error: "Network error occurred", status: 0 };
  }
}

export async function updateGuildConfig(guildId: string, payload: any): Promise<ApiResponse<any>> {
  try {
    const res = await fetch(`/api/guilds/${guildId}/config`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "x-tiffany-csrf": "1",
      },
      body: JSON.stringify(payload),
    });
    
    if (!res.ok) {
      let errorMsg = "Failed to update configuration";
      try {
        const errorData = await res.json();
        errorMsg = errorData.error || errorMsg;
      } catch (e) {}
      return { success: false, error: errorMsg, status: res.status };
    }
    
    const data = await res.json();
    return { success: true, data: data.config };
  } catch (error) {
    return { success: false, error: "Network error occurred", status: 0 };
  }
}
