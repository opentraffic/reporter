package opentraffic.accumulator;

import java.io.IOException;
import java.io.InputStream;

import org.apache.http.HttpEntity;
import org.apache.http.client.ClientProtocolException;
import org.apache.http.client.methods.CloseableHttpResponse;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;
import org.apache.http.util.EntityUtils;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class HttpClient {
  public static <JSON> JSON POST(String url, String body) {
    //try to get the response and parse it
    CloseableHttpResponse response = null;
    JSON j = null;
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
        ObjectMapper mapper = new ObjectMapper();
        j = mapper.readValue(stream, new TypeReference<JSON>(){});
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
    return j;
  }
}
