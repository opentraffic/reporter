package org.opentraffic.reporter;

import java.nio.ByteBuffer;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.apache.http.entity.ContentType;
import org.apache.http.entity.StringEntity;
import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serializer;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;

public class Batch {
  
  public float max_separation; //the maximum distance between the first an any other point
  public List<Point> points;
  
  public Batch() {
    max_separation = 0;
    points = new ArrayList<Point>();
  }
  public Batch(Point p) {
    max_separation = 0;
    points = new ArrayList<Point>();
    points.add(p);
  }

  //get the distance between points using equirectangular approximation
  private static final double rad_per_deg = Math.PI / 180.0;
  private static final double meters_per_deg = 20037581.187 / 180.0;
  private double distance(Point a, Point b){
    double x = (a.lon - b.lon) * meters_per_deg * Math.cos(.5f * (a.lat + b.lat) * rad_per_deg);
    double y = (a.lat - b.lat) * meters_per_deg;
    return Math.sqrt(x * x + y * y);
  }
  
  public void update(Point p) {
    if(points.size() > 0)
      max_separation = (float)Math.max(max_separation, distance(p, points.get(0)));
    points.add(p);
  }
  
  public JsonNode report(String key, String url, int min_dist, int min_size, long min_elapsed) {
    //if it doesnt meet the requirements then bail
    if(max_separation < min_dist || points.size() < min_size ||
        points.get(points.size() - 1).time - points.get(0).time < min_elapsed)
      return null;
    
    //make a post body: uuid json + uuid + trace json + number of points * (single point json) + end of json array and object 
    StringBuilder sb = new StringBuilder();
    sb.ensureCapacity(9 + key.length() + 11 + points.size() * (18 + 18 + 13 + 22 + 1) + 2);
    sb.append("{\"uuid\":\""); sb.append(key); sb.append("\",\"trace\":[");
    for(Point p : points) {
      Point.Serder.put_json(p, sb);
      sb.append(',');
    }
    sb.replace(sb.length() - 1, sb.length() + 1, "]}");
    StringEntity body = new StringEntity(sb.toString(), ContentType.create("application/json", Charset.forName("UTF-8")));
    //go to the server for json
    String response = HttpClient.POST(url, body);
    try {
      //parse the response
      ObjectMapper mapper = new ObjectMapper();
      JsonNode node = mapper.readTree(response);
      JsonNode shape_used = (JsonNode)node.findValue("shape_used");
      //trim the points list based on how much was used
      int trim_to = shape_used == null ? points.size() : shape_used.intValue();
      points.subList(0,trim_to).clear();
      //update the info about whats now in this batch
      max_separation = 0;
      for(int i = 1; i < points.size(); i++)
        max_separation = (float)Math.max(max_separation, distance(points.get(i), points.get(0)));
      return node;
    }
    catch(Exception e) {
      //TODO: maybe we shouldnt trim everything?
      max_separation = 0;
      points.clear();
    }
    //return the raw response string
    return null;    
  }

  public static class Serder implements Serde<Batch> {
    @Override
    public void configure(Map<String, ?> configs, boolean isKey) {     
    }
  
    @Override
    public void close() {
    }
  
    @Override
    public Serializer<Batch> serializer() {
      return new Serializer<Batch>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) {}
        @Override
        public byte[] serialize(String topic, Batch batch) {
          if(batch == null)
            return null;
          ByteBuffer buffer = ByteBuffer.allocate(4 + 4 + Point.SIZE * batch.points.size());
          buffer.putInt(batch.points.size());
          buffer.putFloat(batch.max_separation);
          for(Point p : batch.points)
            Point.Serder.put(p, buffer);
          return buffer.array();
        }
        @Override
        public void close() {}        
      };
    }
  
    @Override
    public Deserializer<Batch> deserializer() {
      return new Deserializer<Batch>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) {}
        @Override
        public Batch deserialize(String topic, byte[] bytes) {
          if(bytes == null)
            return null;
          ByteBuffer buffer = ByteBuffer.wrap(bytes);
          int count = buffer.getInt();
          Batch batch = new Batch();
          batch.points = new ArrayList<Point>(count);
          batch.max_separation = buffer.getFloat();
          for(int i = 0; i < count; i++)
            batch.points.add(Point.Serder.get(buffer));          
          return batch;
        }
        @Override
        public void close() { }
      };
    }
  }
}
