package org.opentraffic.reporter;

import java.nio.ByteBuffer;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;
import java.util.Map;

import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serializer;

public class Point {
  float lat, lon;
  int accuracy;
  long time;
  public static final int SIZE = 4 + 4 + 4 + 8; //keep this up to date
  
  public Point(float lat, float lon, int accuracy, long time) {
    this.lat = lat;
    this.lon = lon;
    this.accuracy = accuracy;
    this.time = time;
  }
  
  public static class Serder implements Serde<Point> {
    public static final DecimalFormat floatFormatter = new DecimalFormat("###.######", new DecimalFormatSymbols(Locale.US));
    public static void put(Point p, ByteBuffer buffer) {
      buffer.putFloat(p.lat);
      buffer.putFloat(p.lon);
      buffer.putInt(p.accuracy);
      buffer.putLong(p.time);
    }
    public static Point get(ByteBuffer buffer) {
      return new Point(buffer.getFloat(), buffer.getFloat(), buffer.getInt(), buffer.getLong());
    }
    public static void put_json(Point p, StringBuilder sb) {
      sb.append("{\"lat\":");
      sb.append(floatFormatter.format(p.lat)).append(",\"lon\":");
      sb.append(floatFormatter.format(p.lon)).append(",\"time\":");
      sb.append(Long.toString(p.time)).append(",\"accuracy\":");
      sb.append(Integer.toString(p.accuracy)).append("}");
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
