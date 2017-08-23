package io.opentraffic.reporter;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serializer;

/*
 * this is used as a key into the in memory map of the current segments that
 * are waiting to be pushed into the datastore
 */
public class TimeQuantisedTile implements Comparable<TimeQuantisedTile>{
  
  public long time_range_start, tile_id;
  public int tile_slice;
  public static final int SIZE = 8 + 8 + 4;
  
  public TimeQuantisedTile(long start, long id, int slice) {
    time_range_start = start;  
    tile_id = id;
    tile_slice = slice;
  }
  
  public static List<TimeQuantisedTile> getTiles(Segment segment, int quantization) {
    List<TimeQuantisedTile> tiles = new ArrayList<TimeQuantisedTile>();
    for(long i = segment.min/quantization; i <= segment.max/quantization; i++) {
      long start = i * quantization;
      tiles.add(new TimeQuantisedTile(start, segment.getTileId(), 0));
    }
    return tiles;
  }
  
  public long getTileIndex() {   
    return (tile_id >> 3) & 0x3FFFFF;
  }
  
  public long getTileLevel() {
    return tile_id & 0x7;
  }
  
  public String toString() {
    return Long.toString(time_range_start) + "_" + Long.toString(tile_id) + "_" + Integer.toString(tile_slice);
  }

  public static class Serder implements Serde<TimeQuantisedTile> {
    @Override
    public void configure(Map<String, ?> configs, boolean isKey) { }    
    @Override
    public void close() { }

    public Serializer<TimeQuantisedTile> serializer() {
      return new Serializer<TimeQuantisedTile>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public byte[] serialize(String topic, TimeQuantisedTile t) {
          if(t == null)
            return null;
          ByteBuffer buffer = ByteBuffer.allocate(SIZE);
          buffer.putLong(t.time_range_start);
          buffer.putLong(t.tile_id);
          buffer.putInt(t.tile_slice);
          return buffer.array();
        }
        @Override
        public void close() { }
      };
    }

    public Deserializer<TimeQuantisedTile> deserializer() {
      return new Deserializer<TimeQuantisedTile>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public TimeQuantisedTile deserialize(String topic, byte[] bytes) {
          if(bytes == null)
            return null;
          ByteBuffer buffer = ByteBuffer.wrap(bytes);
          return new TimeQuantisedTile(buffer.getLong(), buffer.getLong(), buffer.getInt());
        }
        @Override
        public void close() { }
      };
    }
  }

  @Override
  public int compareTo(TimeQuantisedTile o) {
    int time = Long.signum(time_range_start - o.time_range_start) * 100;
    int tile =  Long.signum(tile_id - o.tile_id) * 10;
    return time + tile;
  }

}
