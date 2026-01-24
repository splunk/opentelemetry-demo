// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

interface IRequestParams {
  url: string;
  body?: object;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  queryParams?: Record<string, any>;
  headers?: Record<string, string>;
  timeout?: number; // Timeout in milliseconds
}

const request = async <T>({
  url = '',
  method = 'GET',
  body,
  queryParams = {},
  headers = {
    'content-type': 'application/json',
  },
  timeout,
}: IRequestParams): Promise<T> => {
  const fetchOptions: RequestInit = {
    method,
    body: body ? JSON.stringify(body) : undefined,
    headers,
  };

  // Add timeout if specified
  if (timeout) {
    fetchOptions.signal = AbortSignal.timeout(timeout);
  }

  const response = await fetch(`${url}?${new URLSearchParams(queryParams).toString()}`, fetchOptions);

  const responseText = await response.text();

  if (!!responseText) return JSON.parse(responseText);

  return undefined as unknown as T;
};

export default request;
