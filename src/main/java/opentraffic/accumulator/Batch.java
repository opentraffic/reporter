package opentraffic.accumulator;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serializer;

public class Batch {
  
  public long elapsed;
  public float traveled;
  public static final int SIZE = 4 + 8 + 4; //keep this up to date
  public List<Point> points;
  
  public Batch() {
    elapsed = 0;
    traveled = 0;
    points = new ArrayList<Point>();
  }
  public Batch(Point p) {
    elapsed = 0;
    traveled = 0;
    points = new ArrayList<Point>();
    points.add(p);
  }

  //get the distance between points using equirectangular approximation
  private static final double rad_per_deg = Math.PI / 180;
  private static final double meters_per_deg = 20037581.187 / 180;
  private double distance(Point a, Point b){
    double x = (a.lon - b.lon) * meters_per_deg * Math.cos(.5f * (a.lat + b.lat) * rad_per_deg);
    double y = (a.lat - b.lat) * meters_per_deg;
    return x * x + y * y;
  }
  
  public void update(Point p) {
    Point last = points.get(points.size() - 1);
    elapsed += p.time - last.time;
    traveled += distance(p, last);
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
          ByteBuffer buffer = ByteBuffer.allocate(Batch.SIZE + Point.SIZE * batch.points.size());
          buffer.putInt(batch.points.size());
          buffer.putLong(batch.elapsed);
          buffer.putFloat(batch.traveled);
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
          ByteBuffer buffer = ByteBuffer.wrap(bytes);
          int count = buffer.getInt();
          Batch batch = new Batch();
          batch.points = new ArrayList<Point>(count);
          
          batch.elapsed = buffer.getLong();
          batch.traveled = buffer.getFloat();
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
