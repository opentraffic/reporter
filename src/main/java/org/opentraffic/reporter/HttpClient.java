package org.opentraffic.reporter;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.apache.commons.io.IOUtils;
import org.apache.http.HttpEntity;
import org.apache.http.client.methods.CloseableHttpResponse;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;
import org.apache.http.util.EntityUtils;

public final class HttpClient {
  public static String POST(String url, String body) {
    //try to get the response and parse it
    CloseableHttpResponse response = null;
    String v = null;
    try {
      //build the request
      CloseableHttpClient client = HttpClients.createDefault();
      HttpPost post = new HttpPost(url);
      StringEntity request_entity = new StringEntity(body);
      request_entity.setContentType("application/json");
      post.setEntity(request_entity);
      //make the request
      response = client.execute(post);
      HttpEntity response_entity = response.getEntity();
      if(response.getStatusLine().getStatusCode() == 200) {
        InputStream stream = response_entity.getContent();
        v = IOUtils.toString(stream, StandardCharsets.UTF_8);
      }
      //need to "consume" the response
      EntityUtils.consume(response_entity);
    }//swallow anything
    catch(Exception e) {
      //TODO: log 
    }//always close
    finally {
      if(response != null) 
        try { response.close(); } catch(Exception e){ }
    }
    return v;
  }
}
