package org.opentraffic.reporter;

import java.util.HashMap;
import java.util.LinkedList;
import java.util.ListIterator;

import org.apache.commons.cli.CommandLine;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.processor.Processor;
import org.apache.kafka.streams.processor.ProcessorContext;
import org.apache.kafka.streams.processor.ProcessorSupplier;
import org.apache.kafka.streams.processor.StateStoreSupplier;
import org.apache.kafka.streams.state.KeyValueIterator;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.streams.state.Stores;
import org.apache.log4j.Logger;

import com.fasterxml.jackson.databind.JsonNode;

//here we just take the incoming message, reformat it and key it while doing so
public class BatchingProcessor implements ProcessorSupplier<String, Point> {
  
  private static final String BATCH_STORE_NAME = "batch";
  public static StateStoreSupplier<?> GetStore() {
    return Stores.create(BATCH_STORE_NAME).withStringKeys().withValues(new Batch.Serder()).inMemory().build();
  }
  
  //TODO: get these magic constants from arguments
  private final static Logger logger = Logger.getLogger(BatchingProcessor.class);
  private final long REPORT_TIME = 60;   //seconds
  private final int REPORT_COUNT = 10;   //number of points
  private final int REPORT_DIST = 500;   //meters
  private final long SESSION_GAP = 60000;//milliseconds
  private final String url;

  public BatchingProcessor(CommandLine cmd) {
    logger.debug("Instantiating batching processor");
    url = cmd.getOptionValue("reporter-url");
  }
  
  @Override
  public Processor<String, Point> get() {
    return new Processor<String, Point>() {
      private ProcessorContext context;
      private KeyValueStore<String, Batch> store;
      //TODO: move these timing notions into the key value store
      private LinkedList<Pair<Long, String> > time_to_key;
      private HashMap<String, ListIterator<Pair<Long, String> > > key_to_time_iter;
  
      @SuppressWarnings("unchecked")
      @Override
      public void init(ProcessorContext context) {
        this.context = context;
        this.store = (KeyValueStore<String, Batch>) context.getStateStore(BATCH_STORE_NAME);
        this.time_to_key = new LinkedList<Pair<Long, String> >();
        this.key_to_time_iter = new HashMap<String, ListIterator<Pair<Long, String> > >();
      }
  
      @Override
      public void process(String key, Point point) {
        //clean up stale keys
        clean(key);
        
        //get this batch out of storage and update it
        Batch batch = store.delete(key);
        if(batch == null) {
          logger.debug("Starting new batch for " + key);
          batch = new Batch(point);
        }//we have more than one point now
        else {
          batch.update(point);
          int length = batch.points.size();
          forward(batch.report(key, url, REPORT_DIST, REPORT_COUNT, REPORT_TIME));
          if(batch.points.size() != length)
            logger.debug(key + " was trimmed from " + length + " down to " + batch.points.size());
        }
        
        //put it back if it has something
        if(batch.points.size() > 0)
          this.store.put(key, batch);
        //remove all traces if not
        else {
          ListIterator<Pair<Long, String> > iter = key_to_time_iter.get(key);
          time_to_key.remove(iter);
        }
        
        //move on
        context.commit();
      }
      
      private void clean(String key) {
        //TODO: this might be too blunt, processing delay could cause us to evict stuff from the store
        //below we use the context's timestamp to get the time of the current record we are processing
        //if processing delay occurs this timestamp will deviate from the current time but will still be
        //relative to the time stored in our oldest first list. we may also want to move this potential
        //bottleneck to the punctuate function and do it on a regular interval although the timestamp
        //semantics do change in that configuration

        //go through the keys in stalest first order keys
        while(time_to_key.size() > 0 && context.timestamp() - time_to_key.getFirst().first > SESSION_GAP) {
          //this fogey hasn't been producing much, off to the glue factory
          Pair<Long, String> time_key = time_to_key.pop();
          Batch batch = this.store.get(time_key.second);
          //TODO: dont actually report here, instead insert into a queue that a thread can drain asynchronously
          forward(batch.report(time_key.second, url, 0, 2, 0));
          key_to_time_iter.remove(time_key.second);          
        }
        
        //mark this key as recently having an update
        ListIterator<Pair<Long, String> > iter = key_to_time_iter.get(key);
        if(iter != null)
          time_to_key.remove(iter);
        time_to_key.add(new Pair<Long, String>(context.timestamp(), key));
        iter = time_to_key.listIterator(time_to_key.size() - 1); //O(1)
        key_to_time_iter.put(key,  iter);
      }
      
      private void forward(JsonNode result) {
        JsonNode datastore = result != null ? result.get("datastore") : null;
        JsonNode reports = datastore != null ? datastore.get("reports") : null;
        //TODO: dont ignore the mode...
        //forward on each segment pair
        if(reports != null) {
          for(JsonNode report : reports) {
            try {
              //make a segment pair with one observation
              JsonNode next_id = report.get("next_id");
              Segment segment = new Segment(report.get("id").asLong(),
                  next_id == null || next_id.isNull() ? null : next_id.asLong(), 
                  report.get("t0").asDouble(), report.get("t1").asDouble(),
                  report.get("length").asInt(), report.get("queue_length").asInt());
              //the key is the segment pair so processors will only ever see certain tiles
              //this seeks to maximize the number of possible segments in a given tile
              context.forward(Long.toString(segment.id) + ' ' + 
                  (segment.next_id != null ? Long.toString(segment.next_id) : "null"), segment);
            }
            catch(Exception e) {
              logger.error("Unusable datastore segment pair: " + report.toString() + " (" + e.getMessage() + ")");
            }
          }
        }
      }
  
      @Override
      public void punctuate(long timestamp) {
        //we dont really want to do anything on a regular interval
      }
  
      @Override
      public void close() {
        //take care of the rest of the stuff thats hanging around
        KeyValueIterator<String, Batch> iter = store.all();
        while(iter.hasNext()) {
          KeyValue<String, Batch> kv = iter.next();
          kv.value.report(kv.key, url, 0, 2, 0);
        }
        iter.close();
        //clean up
        store.flush();
      }
    };
  }
}
