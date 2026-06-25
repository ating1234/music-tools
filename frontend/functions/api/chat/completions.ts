export const onRequestPost: PagesFunction<{
  LLM_API_KEY: string;
  LLM_BASE_URL: string;
  LLM_MODEL: string;
}> = async (context) => {
  try {
    const { env, request } = context;

    // 取得環境變數
    const apiKey = env.LLM_API_KEY;
    const baseURL = env.LLM_BASE_URL || 'https://api.openai.com/v1';
    const defaultModel = env.LLM_MODEL || 'gpt-4o-mini';

    if (!apiKey) {
      return new Response(JSON.stringify({ error: 'LLM_API_KEY is not configured on the server.' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // 解析前端傳來的 Request
    const requestData = await request.json() as any;

    // 如果前端沒有指定 model 或我們想強制覆蓋它：
    if (!requestData.model || requestData.model === 'placeholder-model') {
      requestData.model = defaultModel;
    }

    // 重新組裝 LLM 請求網址
    // 去除 baseURL 尾部的斜線，確保路徑正確
    const cleanBaseURL = baseURL.replace(/\/+$/, '');
    const targetURL = `${cleanBaseURL}/chat/completions`;

    // 準備轉發的 Headers
    const headers = new Headers();
    headers.set('Content-Type', 'application/json');
    headers.set('Authorization', `Bearer ${apiKey}`);

    // 發送請求到實際 the LLM
    const llmResponse = await fetch(targetURL, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(requestData),
    });

    // 為了支持 SSE Stream (流式傳輸)
    // 檢查回傳的 Content-Type 是否為 event-stream
    const contentType = llmResponse.headers.get('content-type') || '';
    if (contentType.includes('text/event-stream')) {
      // 串流轉發
      return new Response(llmResponse.body, {
        status: llmResponse.status,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    // 如果是一般的 JSON 回傳
    const responseBody = await llmResponse.text();
    return new Response(responseBody, {
      status: llmResponse.status,
      headers: {
        'Content-Type': 'application/json',
      },
    });

  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message || 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
};
