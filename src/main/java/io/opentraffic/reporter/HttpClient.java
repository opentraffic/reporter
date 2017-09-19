package io.opentraffic.reporter;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.apache.commons.io.IOUtils;
import org.apache.http.Header;
import org.apache.http.HttpEntity;
import org.apache.http.client.HttpRequestRetryHandler;
import org.apache.http.client.config.RequestConfig;
import org.apache.http.client.methods.CloseableHttpResponse;
import org.apache.http.client.methods.HttpEntityEnclosingRequestBase;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.client.methods.HttpPut;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.DefaultHttpRequestRetryHandler;
import org.apache.http.impl.client.HttpClientBuilder;
import org.apache.http.impl.client.HttpClients;
import org.apache.http.message.BasicHeader;
import org.apache.http.util.EntityUtils;
import org.apache.log4j.Logger;

public final class HttpClient {
  private final static Logger logger = Logger.getLogger(HttpClient.class);
  private static final String HMAC_SHA1_ALGORITHM = "HmacSHA1";
  public static String MakeAwsSignature(String sign_me, String secret) throws NoSuchAlgorithmException, InvalidKeyException{
    SecretKeySpec signingKey = new SecretKeySpec(secret.getBytes(), HMAC_SHA1_ALGORITHM);
    Mac mac = Mac.getInstance(HMAC_SHA1_ALGORITHM);
    mac.init(signingKey);
    return Base64.getEncoder().encodeToString(mac.doFinal(sign_me.getBytes()));
  }
  
  public static String PUT(String url, StringEntity body) {
    return PUT(url, body, new Header[0]);
  }
  public static String AwsPUT (String url, String location, StringEntity body, String key, String secret) throws NoSuchAlgorithmException, InvalidKeyException {
    //http://docs.aws.amazon.com/AmazonS3/latest/dev/RESTAuthentication.html#RESTAuthenticationRequestCanonicalization
    String host = url.replaceAll("^.*/", "");
    String bucket = host.substring(0, host.indexOf('.'));    
    String date = java.time.format.DateTimeFormatter.RFC_1123_DATE_TIME.format(ZonedDateTime.now(ZoneId.of("GMT")));
    String resource = '/' + bucket + '/' + location;
    String sign_me = "PUT\n\n" + body.getContentType().getValue() + '\n' + date+ '\n' + resource;
    String signature = MakeAwsSignature(sign_me, secret);
    Header[] headers = {
      new BasicHeader("Host", host),
      new BasicHeader("Date", date),
      new BasicHeader("Authorization", "AWS " + key + ':' + signature)
    };
    return PUT(url + "/" + location, body, headers);
  }
  public static String PUT(String url, StringEntity body, Header[] headers) {
    HttpEntityEnclosingRequestBase request = new HttpPut(url);
    request.setHeaders(headers);
    request.setEntity(body);
    return DO(request);
  }
  public static String POST(String url, StringEntity body) {
    return POST(url, body, new Header[0]);
  }
  public static String POST(String url, StringEntity body, Header[] headers) {
    HttpEntityEnclosingRequestBase request = new HttpPost(url);
    request.setHeaders(headers);
    request.setEntity(body);
    return DO(request);
  }
  public static String DO(HttpEntityEnclosingRequestBase request) {
    //try to get the response and parse it
    CloseableHttpResponse response = null;
    String v = null;
    try {
      //set some timeouts
      RequestConfig.Builder builder = RequestConfig.custom();
      builder.setConnectTimeout(1000);
      builder.setConnectionRequestTimeout(1000);
      builder.setSocketTimeout(10000);
      request.setConfig(builder.build());
      //make the request
      HttpClientBuilder clientBuilder = HttpClients.custom();
      clientBuilder.setRetryHandler(new DefaultHttpRequestRetryHandler(3, false));
      CloseableHttpClient client = clientBuilder.build();
      response = client.execute(request);
      HttpEntity response_entity = response.getEntity();
      InputStream stream = response_entity.getContent();
      v = IOUtils.toString(stream, StandardCharsets.UTF_8);
      //need to "consume" the response
      EntityUtils.consume(response_entity);
    }//swallow anything
    catch(Exception e) {
      logger.error("After 3 attempts couldn't " + request.getMethod() + " to " + request.getURI() + " -> " + e.getMessage());
    }//always close
    finally { 
      try { response.close(); } catch(Exception e){ }
    }
    return v;
  }
}
