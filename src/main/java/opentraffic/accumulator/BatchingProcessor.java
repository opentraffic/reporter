package opentraffic.accumulator;

import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.Map;

import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.processor.Processor;
import org.apache.kafka.streams.processor.ProcessorContext;
import org.apache.kafka.streams.processor.ProcessorSupplier;
import org.apache.kafka.streams.processor.StateStoreSupplier;
import org.apache.kafka.streams.state.KeyValueIterator;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.streams.state.Stores;

//here we just take the incoming message, reformat it and key it while doing so
public class BatchingProcessor implements ProcessorSupplier<String, Point> {
  
  private static final String BATCH_STORE_NAME = "batch";
  public static StateStoreSupplier<?> GetStore() {
    return Stores.create(BATCH_STORE_NAME).withStringKeys().withValues(new Batch.Serder()).inMemory().build();
  }
  
  //TODO: get these magic constants from arguments
  private final long REPORT_TIME = 60000;
  private final int REPORT_COUNT = 10;
  private final int REPORT_DIST = 500;
  private final long SESSION_GAP = 60000;
  private final String url =  "http://localhost:8002/report?";

  public BatchingProcessor(String[] args) {
    //TODO: parse args into private final vars above
  }
  
  @Override
  public Processor<String, Point> get() {
    return new Processor<String, Point>() {
      private ProcessorContext context;
      private KeyValueStore<String, Batch> kvStore;
      private List<Pair<Long, String> > time_to_key;
      private Map<String, ListIterator<Pair<Long, String> > > key_to_time_iter;
  
      @SuppressWarnings("unchecked")
      @Override
      public void init(ProcessorContext context) {
        this.context = context;
        this.kvStore = (KeyValueStore<String, Batch>) context.getStateStore(BATCH_STORE_NAME);
        this.time_to_key = new LinkedList<Pair<Long, String> >();
        this.key_to_time_iter = new HashMap<String, ListIterator<Pair<Long, String> > >();
      }
  
      @Override
      public void process(String key, Point point) {
        //clean up stale keys
        clean(key);
        
        //get this batch out of storage and update it
        Batch batch = this.kvStore.get(key);
        if(batch == null)
          batch = new Batch(point);
        else
         batch.update(point);
        
        //see if it needs reported on
        report(batch);        
        
        //put it back or delete it
        this.kvStore.put(key, batch);
        
        //move on
        context.commit();
      }
      
      private void report(Batch batch) {
        //if it meets the requirements lets act on it
        if(batch.traveled > REPORT_DIST && batch.points.size() > REPORT_COUNT && batch.elapsed > REPORT_TIME) {
          //TODO: do some matching
          //TODO: purge some of the batch
          //TODO: pass something downstream via context.forward
        }
      }
      
      private void clean(String key) {
        Long time = System.currentTimeMillis();
        //go through the stalest keys and if their timestamps are larger
        //than SESSION_GAP report on them and delete them out of the store
        while(time - time_to_key.get(0).first > SESSION_GAP) {
          Batch batch = this.kvStore.get(time_to_key.get(0).second);
          report(batch);
          key_to_time_iter.remove(time_to_key.get(0).second);
          time_to_key.remove(0);
        }
        
        //mark this key as recently having an update
        ListIterator<Pair<Long, String> > iter = key_to_time_iter.get(key);
        time_to_key.remove(iter);
        time_to_key.add(new Pair<Long, String>(time, key));
        iter = time_to_key.listIterator(time_to_key.size() - 1); //O(1)
        key_to_time_iter.put(key,  iter);
      }
  
      @Override
      public void punctuate(long timestamp) {
        //we dont really want to do anything on a regular interval
      }
  
      @Override
      public void close() {
        //take care of the rest of the stuff thats hanging around
        KeyValueIterator<String, Batch> iter = kvStore.all();
        while(iter.hasNext()) {
          KeyValue<String, Batch> kv = iter.next();
          report(kv.value);
        }
        iter.close();
        //clean up
        kvStore.flush();
      }
    };
  }
}
