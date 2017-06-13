package org.opentraffic.reporter;

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
public class TimeQuantisedTiledSegmentPair implements Comparable<TimeQuantisedTiledSegmentPair>{
  
  public long time_range_start, tile_id, segment_id;
  public static final int SIZE = 8 + 8 + 8;
  public Long next_segment_id;
  
  public TimeQuantisedTiledSegmentPair(long start, Segment segment) {
    this.time_range_start = start;
    this.tile_id = segment.getTile();
    this.segment_id = segment.id;
    this.next_segment_id = segment.next_id;
  }
  
  public TimeQuantisedTiledSegmentPair(long start, long tile, long id, Long next) {
    this.time_range_start = start;
    this.tile_id = tile;
    this.segment_id = id;
    this.next_segment_id = next;
  }
  
  public static List<TimeQuantisedTiledSegmentPair> getTiles(Segment segment, int quantization) {
    List<TimeQuantisedTiledSegmentPair> tiles = new ArrayList<TimeQuantisedTiledSegmentPair>();
    for(int i = (int)segment.min/quantization; i <= (int)segment.max/quantization; i++) {
      long start = i * quantization; 
      tiles.add(new TimeQuantisedTiledSegmentPair(start, segment));
    }
    return tiles;
  }

  public static class Serder implements Serde<TimeQuantisedTiledSegmentPair> {
    @Override
    public void configure(Map<String, ?> configs, boolean isKey) { }    
    @Override
    public void close() { }

    public Serializer<TimeQuantisedTiledSegmentPair> serializer() {
      return new Serializer<TimeQuantisedTiledSegmentPair>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public byte[] serialize(String topic, TimeQuantisedTiledSegmentPair t) {
          ByteBuffer buffer = ByteBuffer.allocate(SIZE + (t.next_segment_id != null ? 8 : 0));
          buffer.putLong(t.time_range_start);
          buffer.putLong(t.tile_id);
          buffer.putLong(t.segment_id);
          if(t.next_segment_id != null)
            buffer.putLong(t.next_segment_id);
          return buffer.array();
        }
        @Override
        public void close() { }        
      };
    }

    public Deserializer<TimeQuantisedTiledSegmentPair> deserializer() {
      return new Deserializer<TimeQuantisedTiledSegmentPair>() {
        @Override
        public void configure(Map<String, ?> configs, boolean isKey) { }
        @Override
        public TimeQuantisedTiledSegmentPair deserialize(String topic, byte[] bytes) {
          ByteBuffer buffer = ByteBuffer.wrap(bytes);
          return new TimeQuantisedTiledSegmentPair(buffer.getLong(),  buffer.getLong(), buffer.getLong(),
              buffer.hasRemaining() ? buffer.getLong() : null);
        }
        @Override
        public void close() { }
      };
    }
  }

  @Override
  public int compareTo(TimeQuantisedTiledSegmentPair o) {
    int tile = Long.signum(tile_id - o.tile_id) * 1000;
    int time = Long.signum(time_range_start - o.time_range_start) * 100;
    int seg =  Long.signum(segment_id - o.segment_id) * 10;
    int next = next_segment_id == o.next_segment_id ? 0 : 
      (o.next_segment_id == null ? -1 : (next_segment_id == null ? 1 :
        Long.signum(next_segment_id - o.next_segment_id)));
    return tile + time + seg + next;
  }

}
