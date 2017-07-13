package io.opentraffic.reporter;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Map;

import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serializer;

/*
 * this is used as a histogram entry in a given tile
 */
public class Segment implements Comparable<Segment>{
  
  public static long INVALID_SEGMENT_ID = 0x3fffffffffffL;
  public long id;         //main segment id
  public long next_id;    //optional next, could be invalid
  public long min, max;   //epoch seconds
  public int duration;    //epoch seconds
  public int length;      //meters
  public int queue;       //meters
  public int count;       //how many
  public static final int SIZE = 8 + 8 + 8 + 8 + 4 + 4 + 4 + 4;
  
  public Segment(long id, Long next_id, double start, double end, int length, int queue) {
    this.id = id;
    this.next_id = next_id == null ? INVALID_SEGMENT_ID : next_id;
    this.min = (long)Math.floor(start);
    this.max = (long)Math.ceil(end);
    this.duration = (int)Math.round(end - start);
    this.length = length;
    this.queue = queue;
    this.count = 1;
  }
  
  public Segment(long id, Long next_id, long min, long max, int duration, int length, int queue, int count) {
    this.id = id;
    this.next_id = next_id == null ? INVALID_SEGMENT_ID : next_id;
    this.min = min;
    this.max = max;
    this.duration = duration;
    this.length = length;
    this.queue = queue;
    this.count = 1;
  }
  
  //first 3 bits are hierarchy level then 22 bits of tile id. the rest we want zero'd out
  public long getTileId() {    
    return id & 0x1FFFFFF;
  }
  
  public boolean valid() {
    return count > 0 && min > 0 && max > 0 && duration > 0 && length > 0 && queue >= 0;
  }
  
  @Override
  public String toString() {
    StringBuffer b = new StringBuffer(64);
    appendToStringBuffer(b, "");
    return b.toString();
  }
  
  @Override
  public int compareTo(Segment o) {
    // TODO Auto-generated method stub
    return 0;
  }
  
  public static String columnLayout() {
    return "segment_id,next_segment_id,duration,count,length,queue_length,minimum_timestamp,maximum_timestamp,source,vehicle_type";
  }
  
  public void appendToStringBuffer(StringBuffer buffer, String source) {
    buffer.append('\n');
    buffer.append(Long.toString(id)); buffer.append(',');
    if(next_id != INVALID_SEGMENT_ID)
      buffer.append(next_id);
    buffer.append(',');
    buffer.append(Integer.toString(duration)); buffer.append(',');
    buffer.append(Integer.toString(count)); buffer.append(',');
    buffer.append(Integer.toString(length)); buffer.append(',');
    buffer.append(Integer.toString(queue)); buffer.append(',');
    buffer.append(Long.toString(min)); buffer.append(',');
    buffer.append(Long.toString(max)); buffer.append(',');
    buffer.append(source); buffer.append(',');
    //TODO: parse this in the formatting processor or get it as a program argument
    buffer.append("AUTO");
  }
  
  public static class Serder implements Serde<Segment> {
    @Override
    public void configure(Map<String, ?> configs, boolean isKey) { }    
    @Override
    public void close() { }
    
    public static void put(ByteBuffer buffer, Segment s) {
      buffer.putLong(s.id);
      buffer.putLong(s.next_id);
      buffer.putLong(s.min);
      buffer.putLong(s.max);
      buffer.putInt(s.duration);
      buffer.putInt(s.length);
      buffer.putInt(s.queue);
      buffer.putInt(s.count);
    }
    
    public static Segment get(ByteBuffer buffer) {
      return new Segment(buffer.getLong(), buffer.getLong(), buffer.getLong(), buffer.getLong(), 
          buffer.getInt(), buffer.getInt(), buffer.getInt(), buffer.getInt());
    }

    public Serializer<Segment> serializer() {
      return new Serializer<Segment>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public byte[] serialize(String topic, Segment s) {
          if(s == null)
            return null;
          ByteBuffer buffer = ByteBuffer.allocate(SIZE);
          Serder.put(buffer, s);
          return buffer.array();
        }
        @Override
        public void close() { }        
      };
    }

    public Deserializer<Segment> deserializer() {
      return new Deserializer<Segment>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public Segment deserialize(String topic, byte[] bytes) {
          if(bytes == null)
            return null;
          ByteBuffer buffer = ByteBuffer.wrap(bytes);
          return Serder.get(buffer);
        }
        @Override
        public void close() { }
      };
    }

  }

  public static class ListSerder implements Serde<ArrayList<Segment>> {
    @Override
    public void configure(Map<String, ?> configs, boolean isKey) { }    
    @Override
    public void close() { }

    public Serializer<ArrayList<Segment>> serializer() {
      return new Serializer<ArrayList<Segment>>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public byte[] serialize(String topic, ArrayList<Segment> segments) {
          if(segments == null)
            return null;
          ByteBuffer buffer = ByteBuffer.allocate(4 + SIZE * segments.size());
          buffer.putInt(segments.size());
          for(Segment s : segments)
            Serder.put(buffer, s);
          return buffer.array();
        }
        @Override
        public void close() { }        
      };
    }

    public Deserializer<ArrayList<Segment>> deserializer() {
      return new Deserializer<ArrayList<Segment>>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public ArrayList<Segment> deserialize(String topic, byte[] bytes) {
          if(bytes == null)
            return null;
          ByteBuffer buffer = ByteBuffer.wrap(bytes);
          ArrayList<Segment> segments = new ArrayList<Segment>(buffer.getInt());
          for(int i = 0; i < segments.size(); i++)
            segments.add(Serder.get(buffer));
          return segments;
        }
        @Override
        public void close() { }
      };
    }
  }
  
}
