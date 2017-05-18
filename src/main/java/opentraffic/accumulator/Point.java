package opentraffic.accumulator;

import java.nio.ByteBuffer;
import java.util.Map;

import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serializer;

public class Point {
  float lat, lon;
  int accuracy;
  long time;
  public static final int SIZE = 4 + 4 + 4 + 8; //keep this up to date
  
  public static class Serder implements Serde<Point> {
    public static void put(Point p, ByteBuffer buffer) {
      buffer.putFloat(p.lat);
      buffer.putFloat(p.lon);
      buffer.putInt(p.accuracy);
      buffer.putLong(p.time);
    }
    public static Point get(ByteBuffer buffer) {
      Point p = new Point();
      p.lat = buffer.getFloat();
      p.lon = buffer.getFloat();
      p.accuracy = buffer.getInt();
      p.time = buffer.getLong();
      return p;
    }
    @Override
    public void configure(Map<String, ?> configs, boolean isKey) { }
    @Override
    public void close() { }
    @Override
    public Serializer<Point> serializer() {
      return new Serializer<Point>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public byte[] serialize(String topic, Point p) {
          ByteBuffer buffer = ByteBuffer.allocate(SIZE);
          Serder.put(p, buffer);
          return buffer.array();
        }
        @Override
        public void close() { }        
      };
    }
    @Override
    public Deserializer<Point> deserializer() {
      return new Deserializer<Point>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public Point deserialize(String topic, byte[] bytes) {
          ByteBuffer buffer = ByteBuffer.wrap(bytes);
          return Serder.get(buffer);
        }
        @Override
        public void close() { }
      };
    }    
  }
}
