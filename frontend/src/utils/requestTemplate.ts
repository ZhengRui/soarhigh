export const responseHandlerTemplate = async (response: Response) => {
  if (response.status === 500) {
    throw new Error('Internal Server Error');
  }

  const data = await response.json();

  if (response.status >= 400 && response.status < 500) {
    const err = data.detail ? data.detail : data;
    throw err;
  }

  return data;
};

export const requestTemplate =
  (
    requestConstructor: Function,
    responseHandler: Function = responseHandlerTemplate,
    dataTransformer: Function | null = null,
    requireAuthentication: boolean = false,
    softAuth: boolean = false
  ) =>
  async (...args: any[]) => {
    const { url, method, headers, body } = requestConstructor(...args);
    const headersFinal = headers || new Headers({ Accept: 'application/json' });

    if (requireAuthentication) {
      const token = localStorage.getItem('token');
      if (!token && !softAuth) {
        throw new Error('Not Authorized');
      }

      headersFinal.set('Authorization', `Bearer ${token}`);
    }

    const request = new Request(url, {
      method: method,
      headers: headersFinal,
      body: body,
    });
    const response = await fetch(request);

    const data = await responseHandler(response);

    return dataTransformer ? dataTransformer(data) : data;
  };

export const formConstructor = (data: any) => {
  const formData = new FormData();
  Object.keys(data).forEach((key) => {
    if (Array.isArray(data[key])) {
      // Handle array values (like multiple files)
      data[key].forEach((item: any) => formData.append(key, item));
    } else {
      // Handle non-array values
      formData.append(key, data[key]);
    }
  });

  return formData;
};
